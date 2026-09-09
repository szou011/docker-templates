# Custom Prefect worker image for local development.
#
# Flow code is NOT baked into this image. It is bind-mounted from the host
# at /opt/prefect/flows (see compose.yaml), so edits are picked up without
# rebuilding. Only third-party Python dependencies are baked in.
#
# Rebuild after changing requirements.txt:
#   docker compose build prefect-worker
FROM prefecthq/prefect:3-python3.12

WORKDIR /opt/prefect

# Install flow dependencies into the image.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# /opt/prefect/flows and /opt/prefect/prefect.yaml are provided by bind
# mounts at runtime (see compose.yaml).
