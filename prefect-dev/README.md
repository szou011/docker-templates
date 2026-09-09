# Prefect 3 Local Development Stack (Docker Compose)

A self-contained [Prefect 3](https://docs.prefect.io/) development environment
running in Docker, designed for local flow development against a real Prefect
server with minimal moving parts.

## Design decisions

- **Database on the host** — the stack connects to a Postgres instance running
  on the host machine (not a container), so orchestration metadata (flows,
  deployments, runs, artifacts) persists independently of the Docker stack.
- **No Redis** — a single server process uses Prefect's default in-memory
  messaging broker/cache. Consequence: the API server and background services
  must run in the *same* container (in-memory messaging does not work across
  processes), and the server cannot be scaled horizontally. Fine for dev.
- **Process work pool** — the worker executes flows as subprocesses *inside
  the worker container*. No Docker socket or extra infrastructure required.
- **Flow code via bind mount** — flows are edited on the host and picked up
  immediately; only Python dependencies are baked into the worker image.

## Repository structure

```
.
├── compose.yaml            # The stack: prefect-server + prefect-worker
├── Dockerfile              # Worker image: Prefect base + flow dependencies
├── requirements.txt        # Python deps for your flows (baked into image)
├── prefect.yaml            # Deployment definitions for `prefect deploy`
├── flows/                  # Flow code — bind-mounted into the worker
│   └── example_flow.py     # Example demonstrating results/artifacts
├── data/                   # Persisted results + flow-written files (gitignored)
│   ├── storage/            #   Prefect result storage (serialized blobs)
│   └── exports/            #   Convention: flow-written output files
├── .env.example            # Template for host Postgres credentials
└── .env                    # Your local overrides (gitignored, create from example)
```

## Prerequisites

1. **Docker** (Docker Desktop on macOS/Windows, or Docker Engine on Linux).
2. **Postgres running on the host**, reachable from containers:
   ```sql
   CREATE USER prefect WITH PASSWORD 'prefect';
   CREATE DATABASE prefect OWNER prefect;
   ```
   - *macOS/Windows (Docker Desktop)*: `host.docker.internal` reaches
     localhost-bound services out of the box.
   - *Linux*: set `listen_addresses = '0.0.0.0'` (or the docker bridge IP) in
     `postgresql.conf` and add a `pg_hba.conf` entry for the docker subnet
     (e.g. `172.17.0.0/16`). The compose file already maps
     `host.docker.internal` to the host gateway.
3. **`.env` file** (only if using non-default credentials):
   ```bash
   cp .env.example .env   # then edit values
   ```

Schema migrations run automatically when the server starts.

## Usage

### Start the stack

```bash
docker compose build prefect-worker   # builds the worker image (deps baked in)
docker compose up -d
```

- UI and API: <http://localhost:4200>
- Logs: `docker compose logs -f`

On first boot the worker automatically creates the `local-pool` process work
pool (`--type process` flag; on subsequent starts the flag is ignored).

### Register deployments

Run `prefect deploy` **from inside the worker container** so paths resolve
identically at deploy time and run time:

```bash
docker compose exec prefect-worker prefect deploy --all
```

This registers every deployment defined in `prefect.yaml` (idempotent —
re-run it after changing schedules, entrypoints, or parameters).

### Trigger a run

```bash
docker compose exec prefect-worker prefect deployment run 'hello-flow/example'
```

Then watch it in the UI, or check the persisted outputs on the host:

```bash
ls data/storage/    # serialized flow/task results (opaque names, internal use)
ls data/exports/    # files the example flow wrote itself
```

### Stop the stack

```bash
docker compose stop      # containers stay stopped across Docker restarts
docker compose down      # stop and remove containers (data/ and DB persist)
```

## Development workflow

| You changed... | Action required |
|---|---|
| Files in `flows/` | Nothing — bind mount picks edits up immediately |
| Deployments in `prefect.yaml` | Re-run `prefect deploy --all` (see above) |
| `requirements.txt` | `docker compose build prefect-worker && docker compose up -d prefect-worker` |
| Postgres credentials | Edit `.env`, then `docker compose up -d` |

**Adding a new flow**: drop a file in `flows/`, add a deployment entry in
`prefect.yaml` (entrypoint is relative to `/opt/prefect` in the container,
e.g. `flows/my_flow.py:my_flow`), re-run `prefect deploy --all`.

**Deploying from the host instead**: possible, but requires Prefect installed
locally and `PREFECT_API_URL=http://localhost:4200/api`. Beware that
deployment paths are recorded from where you deploy — running inside the
worker container avoids the whole class of host-vs-container path mismatches.

## Persistence model

| Data | Where it lives | Survives `docker compose down`? |
|---|---|---|
| Flows, deployments, run history, UI artifacts (markdown/table/link) | Host Postgres | ✅ |
| Serialized flow/task results (`persist_result`) | `./data/storage` via bind mount (`PREFECT_LOCAL_STORAGE_PATH`) | ✅ |
| Files your flows write | `./data` (convention: flows write under `/opt/prefect/data`) | ✅ |
| Flow code | `./flows` on the host | ✅ |
| Server container itself | Stateless | n/a |

Notes:

- `PREFECT_RESULTS_PERSIST_BY_DEFAULT=true` is set on the worker, so results
  are persisted globally unless a flow/task opts out with
  `persist_result=False`.
- Result files are serialized blobs (pickle/LZMA) with opaque keys — they
  back Prefect features like retries, caching, and reading run return values;
  they are not human-readable output. For human-facing output use artifacts
  (stored in Postgres, shown in the UI) or write files to `/opt/prefect/data`.
- For multi-worker or production setups, replace local storage with a remote
  storage block (e.g. S3 via `PREFECT_DEFAULT_RESULT_STORAGE_BLOCK`).

## Operational notes

- **Restart policy**: both services use `unless-stopped` — they recover from
  crashes and Docker daemon restarts, but stay down after a deliberate
  `docker compose stop`.
- **Server healthcheck**: `GET /api/health`; the worker waits for the server
  to be healthy before starting.
- **Worker concurrency**: add `--limit N` to the worker command to cap
  parallel flow runs.
- **Dependencies**: add third-party packages your flows import to
  `requirements.txt` and rebuild — the bind mount only provides flow *code*,
  not packages.

## Known limitations / TODO

- **Server image floats on `prefecthq/prefect:3-latest`** while the worker is
  pinned to the `3-python3.12` base — the two can drift apart. Pin the server
  to the same tag for reproducibility.
- **No authentication** — the server API is unauthenticated; bind to localhost
  only (the default port mapping does) and don't expose it on a network.
- **Single server process** — by design (in-memory messaging). Add Redis and
  split background services into their own container if you ever need high
  availability.
- **Process worker shares the container's filesystem and resources** — flows
  with heavy or conflicting system dependencies may warrant switching to a
  Docker work pool (requires mounting `/var/run/docker.sock` and installing
  `prefect-docker` in the worker image).
