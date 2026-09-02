# Apache Airflow 3.x — Local Development (Docker Compose)

A simple, reasonably secure single-host Airflow 3.x setup for development.

- **Executor:** `LocalExecutor`
- **Database:** PostgreSQL running **on the host** (not containerized), reached
  from containers via `host.docker.internal`
- **Auth:** FAB Auth Manager (`apache-airflow-providers-fab`, Flask
  AppBuilder). Users live in the metadata DB; the admin user is created by
  `airflow-init` from the `AIRFLOW_ADMIN_*` env vars
- **Services:** `airflow-init` (DB migration + admin user),
  `airflow-dag-processor` (parses DAG files), `airflow-triggerer` (runs
  deferrable operators), `airflow-scheduler`, `airflow-apiserver`
  (UI + REST API), plus an `airflow-cli` debug-profile service for ad-hoc
  Airflow CLI commands

## Host PostgreSQL prerequisites

There is **no** `postgres` service in this stack. Before first run, configure
PostgreSQL on the host once:

- `postgresql.conf`: `listen_addresses = '*'` (or at least the Docker bridge
  address)
- `pg_hba.conf`: allow the Docker subnet, e.g.
  `host all all 172.16.0.0/12 scram-sha-256`, then reload Postgres
- Create the role and database matching `POSTGRES_USER` / `POSTGRES_DB` in
  `.env` yourself — `airflow-init` only runs migrations, it does not create
  the role/db.

From inside containers the host is reachable as `host.docker.internal` on
Docker Desktop (Mac/Windows) and WSL2; on native Linux the compose file maps
it via `extra_hosts: host-gateway`.

> **Note:** the API server port is published as `0.0.0.0:8080:8080`, so the
> UI/API is intentionally reachable from your LAN at `http://<host-ip>:8080`.
> See *Security notes* for the implications and how to restrict it.

---

## Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose`, not `docker-compose`).
- Python available on the host (only to generate the keys below), or generate
  them any other way you like.

---

## First-run setup

All commands are run from this directory (`airflow-dev/`).

### 1. Create the local directories

Docker bind-mounts these. If they don't exist, Docker creates them owned by
`root`, which the Airflow container (running as your UID) then can't write to.
Create them yourself first so they're owned by you:

```bash
mkdir -p dags plugins logs config data/raw data/processed data/exception
```

### 2. Create your `.env`

```bash
cp .env.example .env
```

Then edit `.env` and fill in the values:

| Variable | How to set it |
|---|---|
| `AIRFLOW_UID` | Run `echo $(id -u)` and paste the result (Linux/WSL2). Ensures bind-mounted files are owned by you. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Credentials of the **host** PostgreSQL instance; the role and database must already exist (see above). |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Defaults (`host.docker.internal` / `5432`) are usually fine; change only if your host Postgres differs. |
| `AIRFLOW__CORE__FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AIRFLOW__API__SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `AIRFLOW_ADMIN_USERNAME` / `AIRFLOW_ADMIN_PASSWORD` | Credentials for the initial admin account, created by `airflow-init`. |
| `AIRFLOW_ADMIN_FIRSTNAME` / `AIRFLOW_ADMIN_LASTNAME` / `AIRFLOW_ADMIN_EMAIL` | Optional; have sensible defaults. |
| `AIRFLOW__API_AUTH__JWT_SECRET` / `AIRFLOW__API_AUTH__JWT_ISSUER` | Signs REST API JWTs. `JWT_SECRET` is required (no default) — generate one like the secret key above. `JWT_ISSUER` defaults to `airflow`. |

> Compose will refuse to start if `FERNET_KEY`, `API__SECRET_KEY` or
> `JWT_SECRET` are empty — this is intentional, to avoid booting with a broken
> or forgeable-auth config.
>
> `.env` is injected into the containers via `env_file`, so any
> `AIRFLOW_CONN_*` / custom variables you add there are visible to your DAGs.

### 3. Build and start

```bash
docker compose build
docker compose up -d
```

`airflow-init` runs `airflow db migrate` (core tables), `airflow fab-db
migrate` (FAB auth tables — separate in Airflow 3.x) and creates the admin
user from the `AIRFLOW_ADMIN_*` env vars, then exits. The dag-processor,
triggerer, scheduler and API server start once it completes successfully.

> **Note (Airflow 3.x):** DAG files are parsed by the standalone
> `airflow-dag-processor` service, not the scheduler. It must be running for
> DAGs dropped into `dags/` to be detected and scheduled.

### 4. Log in

Open <http://localhost:8080> and log in with `AIRFLOW_ADMIN_USERNAME` and
`AIRFLOW_ADMIN_PASSWORD` from `.env`.

- REST API base: <http://localhost:8080/api/v2>

---

## Day-to-day usage

```bash
docker compose ps                            # service status
docker compose logs -f airflow-scheduler     # follow scheduler logs
docker compose down                          # stop (keeps the host database)
docker compose build                         # rebuild after changing requirements.txt
```

- **DAGs:** drop `.py` files into `dags/`; the `airflow-dag-processor` service
  picks them up.
- **Plugins:** drop into `plugins/`.
- **Data:** DAGs can read/write `data/raw`, `data/processed`, `data/exception`
  (mounted at `/opt/airflow/data/...` in the containers).
- **Python deps:** add to `requirements.txt`, then `docker compose build` and
  restart.
- **Ad-hoc CLI commands:** an `airflow-cli` service runs under the `debug`
  profile (it never starts with a normal `up`):

  ```bash
  docker compose --profile debug run --rm airflow-cli airflow dags list
  docker compose --profile debug run --rm airflow-cli airflow users list
  ```

---

## Adding more users

Users are stored in the metadata DB and managed with the `airflow users` /
`airflow roles` CLI (or via the UI under **Security → Users**):

```bash
docker compose --profile debug run --rm airflow-cli airflow users create \
  --username analyst --password 'choose-a-strong-password' \
  --firstname Ana --lastname Lyst --email analyst@example.com \
  --role Viewer
```

FAB roles: `Admin`, `Op`, `User`, `Viewer` (plus custom roles via
`airflow roles create`). Auth behaviour (rate limiting, RBAC, OAuth, ...) is
configured in `config/webserver_config.py` — FAB auto-generates a default on
first run if the file is absent, and the `config/` mount is read-write so it
persists.

---

## Security notes

- The UI/API is published on **all interfaces** (`0.0.0.0:8080:8080`) so it
  is reachable from the LAN. Because of that:
  - Use a strong `AIRFLOW_ADMIN_PASSWORD` — the FAB login page is reachable by
    anyone on the LAN.
  - Traffic is plain HTTP — acceptable on a trusted dev LAN, not beyond it.
  - To restrict the UI to this machine, change the port mapping in
    `compose.yaml` to `127.0.0.1:8080:8080`.
- The metadata database is your host PostgreSQL — network access is governed
  by `pg_hba.conf`. Keep the allowed subnet as tight as practical.
- `.env` holds secrets (DB password, Fernet key, API secret key, admin
  password) and is git-ignored. Keep it that way.
- The Fernet key encrypts connection/variable secrets in the metadata DB. If
  you lose it, those secrets become unrecoverable; if you rotate it, existing
  encrypted values can't be decrypted.
- `AIRFLOW__API_AUTH__JWT_SECRET` has no default and Compose refuses to start
  without it — a guessable JWT secret would let anyone on the LAN forge REST
  API tokens.

---

## Troubleshooting

- **Compose exits immediately complaining about `FERNET_KEY` / `SECRET_KEY`** —
  you haven't filled them in `.env`. See step 2.
- **`airflow-init` fails to connect to Postgres** — the DB is on the host, not
  in Docker. Check, in order:
  1. Postgres is running on the host and listening on more than `localhost`
     (`listen_addresses` in `postgresql.conf`).
  2. `pg_hba.conf` allows the Docker subnet (`172.16.0.0/12` typically) —
     reload Postgres after editing.
  3. The role/database in `POSTGRES_USER` / `POSTGRES_DB` actually exist.
  4. From a container: `docker compose --profile debug run --rm airflow-cli bash -c "getent hosts host.docker.internal"`.
- **Can't log in** — the admin user is created only when `airflow-init` runs
  successfully. Check `docker compose logs airflow-init`, and verify the user
  exists with
  `docker compose --profile debug run --rm airflow-cli airflow users list`.
  If you changed `AIRFLOW_ADMIN_*` after the first run, re-run the init
  container (`docker compose up airflow-init`) or update the user via the CLI.
- **Permission denied writing logs** — the bind-mounted dirs are owned by root.
  Set `AIRFLOW_UID` in `.env` to your `id -u` and recreate the dirs (step 1).
- **DAGs in `dags/` don't appear in the UI** — make sure the
  `airflow-dag-processor` service is running (`docker compose ps`). In Airflow
  3.x the scheduler does not parse DAG files; the dag-processor does. Check its
  logs with `docker compose logs -f airflow-dag-processor`.
- **A task is stuck in the `deferred` state** — the `airflow-triggerer`
  service isn't running. Deferrable operators hand off to the triggerer to
  resume; check `docker compose ps` and
  `docker compose logs -f airflow-triggerer`.
- **`http://localhost:8080` unreachable from Windows (WSL2)** — restart WSL with
  `wsl --shutdown`; the localhost relay occasionally needs a kick. (Only
  relevant if you switch the port mapping to loopback.)
