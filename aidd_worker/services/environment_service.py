"""
AIDD Worker - Computational Environment Capture & Fingerprint (v1.4.0)
"""

import sys
import os
import json
import hashlib
import platform
from typing import Dict, Any

from aidd_worker import config
from aidd_worker.services.capability_service import get_all_capabilities

def compute_environment_sha256(env_dict: dict) -> str:
    """
    Computes deterministic SHA-256 fingerprint from normalized environment manifest.
    """
    norm_dict = {
        "os": env_dict.get("os"),
        "architecture": env_dict.get("architecture"),
        "python_version": env_dict.get("python_version"),
        "worker_version": env_dict.get("worker_version"),
        "scientific_capabilities": {
            "rdkit": env_dict.get("scientific_capabilities", {}).get("rdkit", {}).get("version"),
            "vina": env_dict.get("scientific_capabilities", {}).get("autodock_vina", {}).get("version"),
            "openbabel": env_dict.get("scientific_capabilities", {}).get("openbabel", {}).get("version")
        },
        "core_libraries": env_dict.get("core_libraries", {})
    }
    raw_str = json.dumps(norm_dict, sort_keys=True)
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

def capture_full_environment() -> dict:
    caps = get_all_capabilities()
    
    packages = {}
    for pkg in ["numpy", "scipy", "pandas", "fastapi", "pydantic", "rdkit", "matplotlib", "torch", "sklearn", "xgboost"]:
        try:
            mod = __import__(pkg)
            packages[pkg] = getattr(mod, "__version__", "installed")
        except ImportError:
            packages[pkg] = "not_installed"

    env_data = {
        "worker_id": config.WORKER_ID,
        "worker_version": config.WORKER_VERSION,
        "api_version": config.API_VERSION,
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "processor": platform.processor() or "x86_64",
        "cpu_cores": os.cpu_count() or 1,
        "python_version": platform.python_version(),
        "python_compiler": platform.python_compiler(),
        "scientific_capabilities": caps["scientific_software"],
        "core_libraries": packages,
        "storage_root": config.JOBS_DIR
    }
    env_data["environment_sha256"] = compute_environment_sha256(env_data)
    return env_data
