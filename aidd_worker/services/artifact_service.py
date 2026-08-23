"""
AIDD Worker - Artifact Management & Cryptographic Hashing (SHA-256)
"""

import os
import io
import hashlib
from typing import Dict, Any, List

from aidd_worker import config
from aidd_worker.models import ArtifactInfo

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
    job_dir = os.path.join(config.JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    file_path = os.path.join(job_dir, filename)
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
