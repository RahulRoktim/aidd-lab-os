# Multi-Stage Reproducible Scientific Container for AIDD Worker
# Stage 1: Build scientific environment with conda-forge RDKit & AutoDock Vina
FROM continuumio/miniconda3@sha256:1808b31ef43e9c521cde5884ba4df9ec26d8d503a314cea787590f8550358a63 AS builder

LABEL maintainer="AIDD Lab OS Computational Chemistry Core <core@aidd-lab-os.org>"
LABEL version="1.4.0"
LABEL description="Attested Docker scientific worker with native RDKit, AutoDock Vina, and OpenBabel"

WORKDIR /build

COPY aidd_worker/environment.yml .
COPY aidd_worker/release_attestation.json .
COPY aidd_worker/verify_release_environment.py .
RUN conda env create -f environment.yml && \
    /opt/conda/envs/aidd-worker-env/bin/python verify_release_environment.py \
      --metadata release_attestation.json \
      --prefix /opt/conda/envs/aidd-worker-env && \
    conda clean -afy

# Stage 2: Runtime image
FROM continuumio/miniconda3@sha256:1808b31ef43e9c521cde5884ba4df9ec26d8d503a314cea787590f8550358a63 AS runtime

WORKDIR /app

# Copy conda environment from builder
COPY --from=builder /opt/conda/envs/aidd-worker-env /opt/conda/envs/aidd-worker-env

# Environment configuration
ENV PATH="/opt/conda/envs/aidd-worker-env/bin:$PATH" \
    AIDD_WORKER_PORT=8001 \
    AIDD_WORKER_HOST=0.0.0.0 \
    AIDD_WORKER_JOBS_DIR=/data/jobs \
    PYTHONUNBUFFERED=1

# Create persistent storage mount points
RUN mkdir -p /data/jobs /data/artifacts

COPY aidd_worker/ ./aidd_worker/
COPY app/ ./app/

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:8001/health || exit 1

ENTRYPOINT ["python3", "-m", "uvicorn", "aidd_worker.main:app", "--host", "0.0.0.0", "--port", "8001"]
