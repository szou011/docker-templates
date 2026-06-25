# =============================================================================
# Dockerfile — Apache Airflow 3.x custom image
# Extends the official image with project-specific Python dependencies.
# =============================================================================

ARG AIRFLOW_VERSION=3.0.1
FROM apache/airflow:${AIRFLOW_VERSION}

# Switch to root to install any OS-level dependencies (if needed)
USER root

# Example: install OS packages here if required
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     <your-os-package> \
#  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Switch back to the airflow user for pip installs
USER airflow

# Copy and install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
