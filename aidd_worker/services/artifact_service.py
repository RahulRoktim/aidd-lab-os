"""
AIDD Worker - Artifact Management & Cryptographic Hashing (SHA-256)
"""

import os
import io
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List

from aidd_worker import config
from aidd_worker.models import ArtifactInfo

_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def resolve_job_directory(job_id: str, create: bool = False) -> str:
    if not isinstance(job_id, str) or not _SAFE_JOB_ID.fullmatch(job_id):
        raise ValueError("Unsafe job identifier")
    root = Path(config.JOBS_DIR).resolve()
    job_dir = (root / job_id).resolve()
    if job_dir.parent != root:
        raise ValueError("Resolved job directory escapes the jobs root")
    if create:
        job_dir.mkdir(parents=True, exist_ok=True)
    return str(job_dir)


def resolve_job_path(job_id: str, filename: str, create_directory: bool = False) -> str:
    if (
        not isinstance(filename, str)
        or filename in {".", ".."}
        or ".." in filename
        or not _SAFE_FILENAME.fullmatch(filename)
    ):
        raise ValueError("Unsafe artifact filename")
    job_dir = Path(resolve_job_directory(job_id, create=create_directory))
    file_path = (job_dir / filename).resolve()
    if file_path.parent != job_dir:
        raise ValueError("Resolved artifact path escapes the job directory")
    return str(file_path)

def compute_sha256(data: str or bytes) -> str:
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def compute_file_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def save_job_artifact(job_id: str, filename: str, content: str or bytes, file_type: str = "text") -> ArtifactInfo:
    file_path = resolve_job_path(job_id, filename, create_directory=True)
    mode = 'wb' if isinstance(content, bytes) else 'w'
    with open(file_path, mode, encoding=None if isinstance(content, bytes) else 'utf-8') as f:
        f.write(content)
        
    size_bytes = os.path.getsize(file_path)
    sha256 = compute_file_sha256(file_path)
    
    return ArtifactInfo(
        name=filename,
        file_type=file_type,
        size_bytes=size_bytes,
        sha256_hash=sha256,
        url_path=f"/jobs/{job_id}/artifacts/{filename}"
    )

def create_checksum_manifest(job_id: str, artifacts: List[ArtifactInfo]) -> ArtifactInfo:
    lines = [f"{a.sha256_hash}  {a.name}" for a in artifacts]
    content = "\n".join(lines) + "\n"
    return save_job_artifact(job_id, "checksums.sha256", content, file_type="checksum")
