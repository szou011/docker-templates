# Apache Airflow 3.x — Local Development (Docker Compose)

A simple, reasonably secure single-host Airflow 3.x setup for development.

- **Executor:** `LocalExecutor`
- **Database:** PostgreSQL 18 (internal network only, not exposed)
- **Auth:** `SimpleAuthManager` (Airflow 3.x default), credentials in a
  JSON file under `config/`
- **Services:** `postgres`, `airflow-init` (DB migration),
  `airflow-dag-processor` (parses DAG files), `airflow-scheduler`,
  `airflow-apiserver` (UI + REST API)

The UI is bound to `127.0.0.1:8080` so it is **not** reachable from your LAN.
On WSL2 it is still reachable from Windows at <http://localhost:8080> via WSL2's
localhost forwarding.

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
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Defaults are fine for local dev; change the password if you like. Postgres is not exposed outside the Docker network. |
| `AIRFLOW__CORE__FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AIRFLOW__API__SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `AIRFLOW_ADMIN_USERNAME` | Username for the admin account (default `admin`). |

> Compose will refuse to start if `FERNET_KEY` or `API__SECRET_KEY` are empty —
> this is intentional, to avoid booting with a broken config.

### 3. Create the password file

`SimpleAuthManager` keeps admin credentials in `config/passwords.json`. The
`config/` directory is mounted **read-write**, because SimpleAuthManager rewrites
this file on startup. The JSON key must match `AIRFLOW_ADMIN_USERNAME`:

```bash
echo '{"admin": "choose-a-strong-password"}' > config/passwords.json
```

If you skip this and leave the file absent, SimpleAuthManager will generate a
random password on first boot and write it here — read it back with
`cat config/passwords.json`.

This file contains a secret and is **git-ignored** — never commit it. The file
must be writable by the container UID (`AIRFLOW_UID`); if it's owned by a
different user you'll see `Errno 30 (read-only)` or `Errno 13 (permission)`.

### 4. Build and start

```bash
docker compose build
docker compose up -d
```

`airflow-init` runs the DB migration and exits; the dag-processor, scheduler
and API server start once it completes successfully and Postgres is healthy.

> **Note (Airflow 3.x):** DAG files are parsed by the standalone
> `airflow-dag-processor` service, not the scheduler. It must be running for
> DAGs dropped into `dags/` to be detected and scheduled.

### 5. Log in

Open <http://localhost:8080> and log in with `AIRFLOW_ADMIN_USERNAME` and the
password you set in `config/passwords.json`.

- REST API base: <http://localhost:8080/api/v2>

---

## Day-to-day usage

```bash
docker compose ps                 # service status
docker compose logs -f scheduler  # follow scheduler logs
docker compose down               # stop (keeps the database volume)
docker compose down -v            # stop and DELETE the database volume
docker compose build              # rebuild after changing requirements.txt
```

- **DAGs:** drop `.py` files into `dags/`; the `airflow-dag-processor` service
  picks them up.
- **Plugins:** drop into `plugins/`.
- **Data:** DAGs can read/write `data/raw`, `data/processed`, `data/exception`
  (mounted at `/opt/airflow/data/...` in the containers).
- **Python deps:** add to `requirements.txt`, then `docker compose build` and
  restart.

---

## Adding more users

Edit `.env` (or the compose env) so `SIMPLE_AUTH_MANAGER_USERS` lists each user
as `username:Role` (roles: `Admin`, `Op`, `User`, `Viewer`), e.g.:

```
admin:Admin,analyst:Viewer
```

Then add a matching entry for each user in `config/passwords.json`:

```json
{ "admin": "...", "analyst": "..." }
```

Restart the stack afterwards.

---

## Security notes

- The UI/API is bound to loopback (`127.0.0.1:8080`). To expose it on your LAN,
  change the port mapping in `docker-compose.yaml` to `0.0.0.0:8080:8080`.
- Postgres has no published port — it is only reachable on the internal
  `airflow-network`.
- `.env` and `config/passwords.json` hold secrets and are git-ignored. Keep them
  that way.
- The Fernet key encrypts connection/variable secrets in the metadata DB. If you
  lose it, those secrets become unrecoverable; if you rotate it, existing
  encrypted values can't be decrypted.

---

## Troubleshooting

- **Compose exits immediately complaining about `FERNET_KEY` / `SECRET_KEY`** —
  you haven't filled them in `.env`. See step 2.
- **Can't log in** — confirm the username in `config/passwords.json` exactly
  matches `AIRFLOW_ADMIN_USERNAME`, and that the user appears in
  `SIMPLE_AUTH_MANAGER_USERS`.
- **Permission denied writing logs** — the bind-mounted dirs are owned by root.
  Set `AIRFLOW_UID` in `.env` to your `id -u` and recreate the dirs (step 1).
- **`OSError [Errno 30] read-only file system: .../config/passwords.json`** —
  SimpleAuthManager needs to write this file on startup. The `config/` dir must
  be mounted read-write (it is, by default — don't add `:ro`). `Errno 13` on the
  same path means the file is owned by a different user than `AIRFLOW_UID`;
  `chown`/`chmod` it so the container UID can write.
- **DAGs in `dags/` don't appear in the UI** — make sure the
  `airflow-dag-processor` service is running (`docker compose ps`). In Airflow
  3.x the scheduler does not parse DAG files; the dag-processor does. Check its
  logs with `docker compose logs -f dag-processor`.
- **`http://localhost:8080` unreachable from Windows (WSL2)** — restart WSL with
  `wsl --shutdown`; the localhost relay occasionally needs a kick.
- **Postgres won't start after an image change** — Postgres 18 stores data under
  `/var/lib/postgresql` (version-specific layout). Don't override `PGDATA` in
  this compose file; if you're migrating an older volume, follow the official
  `postgres` image upgrade notes.
