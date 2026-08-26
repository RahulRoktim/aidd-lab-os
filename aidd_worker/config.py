"""
AIDD Worker - Configuration & Runtime Settings (v1.4.0)
"""

import os
import socket
import uuid
import json

WORKER_VERSION = "1.4.0"
API_VERSION = "v1"
WORKER_ID = os.environ.get("AIDD_WORKER_ID", f"worker_{socket.gethostname()}_{uuid.uuid4().hex[:6]}")
HOST = os.environ.get("AIDD_WORKER_HOST", "0.0.0.0")
PORT = int(os.environ.get("AIDD_WORKER_PORT", "8001"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RELEASE_ATTESTATION_PATH = os.path.join(BASE_DIR, "release_attestation.json")
with open(RELEASE_ATTESTATION_PATH, "r", encoding="utf-8") as _release_file:
    RELEASE_ATTESTATION = json.load(_release_file)

# Persistent storage configuration
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DATA_DIR = os.environ.get("AIDD_DATA_DIR", "/data" if os.path.exists("/data") else DEFAULT_DATA_DIR)

JOBS_DIR = os.environ.get("AIDD_WORKER_JOBS_DIR", os.path.join(DATA_DIR, "jobs"))
ARTIFACTS_DIR = os.environ.get("AIDD_WORKER_ARTIFACTS_DIR", os.path.join(DATA_DIR, "artifacts"))

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# The runtime may select a candidate path, but trust is anchored exclusively in
# repository-controlled release metadata and never in PATH or request data.
VINA_EXECUTABLE = os.environ.get(
    "VINA_BIN",
    RELEASE_ATTESTATION["vina"]["expected_path"],
)
OBABEL_EXECUTABLE = os.environ.get("OBABEL_BIN", "obabel")

# Job execution safety limits
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
MAX_DOCKING_TIMEOUT_SECONDS = int(os.environ.get("MAX_DOCKING_TIMEOUT", "600"))
MAX_LIGAND_COUNT_PER_BATCH = int(os.environ.get("MAX_LIGAND_BATCH", "2500"))
MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024))) # 25MB

ALLOWED_JOB_TYPES = ["descriptors", "standardize", "docking", "fingerprint"]
