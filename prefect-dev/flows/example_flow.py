"""Example flow to verify the stack end-to-end.

Demonstrates:
- persist_result=True: the flow's return value is serialized into
  /opt/prefect/data/storage (bind-mounted to ./data on the host, see
  PREFECT_LOCAL_STORAGE_PATH in compose.yaml). Note: PREFECT_RESULTS_
  PERSIST_BY_DEFAULT=true already enables this globally; the explicit
  decorator argument is shown here for documentation purposes.
- Writing a data artifact: files your flow writes itself are NOT managed
  by Prefect's result storage. Convention in this stack: write outputs
  under /opt/prefect/data (./data on the host).
- A markdown artifact: stored in Postgres and visible in the UI.

Register the deployment (from inside the worker container, so paths
resolve the same way at deploy time and run time):

    docker compose exec prefect-worker prefect deploy --all

Trigger a run:

    docker compose exec prefect-worker prefect deployment run 'hello-flow/example'
"""

from datetime import datetime, timezone
from pathlib import Path

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact

# Flow-written outputs live here; bind-mounted to ./data on the host.
DATA_DIR = Path("/opt/prefect/data")


@task(persist_result=True)
def build_greeting(name: str) -> str:
    return f"Hello, {name}!"


@flow(name="hello-flow", log_prints=True, persist_result=True)
def hello_flow(name: str = "world") -> str:
    logger = get_run_logger()

    message = build_greeting(name)
    logger.info(message)

    # A file the flow writes itself (not Prefect result storage).
    exports_dir = DATA_DIR / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    out_file = exports_dir / f"greeting-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.txt"
    out_file.write_text(message + "\n")
    logger.info("Wrote %s", out_file)

    # A human-readable artifact, stored in Postgres, visible in the UI.
    create_markdown_artifact(
        key="greeting",
        markdown=f"**{message}**\n\nOutput file: `{out_file}`",
        description="Example artifact from hello-flow",
    )

    return message


if __name__ == "__main__":
    hello_flow()
