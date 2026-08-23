"""
AIDD Worker - Capability Discovery & Scientific Tool Detection
"""

import sys
import shutil
import subprocess
import platform
import os
from typing import Dict, Any

from aidd_worker import config

def detect_rdkit() -> dict:
    try:
        import rdkit
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski, QED
        return {
            "installed": True,
            "version": getattr(rdkit, "__version__", "unknown"),
            "production_ready": True,
            "backend": "C++ Native Extension",
            "features": ["SMILES", "Descriptors", "Lipinski", "QED", "Fingerprints", "2D Depiction", "Standardizer"]
        }
    except ImportError:
        return {
            "installed": False,
            "version": None,
            "production_ready": False,
            "backend": "Pure-Python Reference Engine (Non-Production Fallback)",
            "features": ["Reference SMILES Parser", "Calibrated Descriptors"]
        }

def detect_vina() -> dict:
    vina_path = shutil.which(config.VINA_EXECUTABLE)
    if not vina_path:
        # Check standard binary locations
        for p in ["/usr/bin/vina", "/usr/local/bin/vina", "/opt/vina/bin/vina", os.path.expanduser("~/miniconda3/bin/vina"), os.path.expanduser("~/miniforge3/bin/vina")]:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                vina_path = p
                break

    if not vina_path:
        return {
            "installed": False,
            "path": None,
            "version": None,
            "production_ready": False
        }

    # Extract version
    version_str = "unknown"
    try:
        res = subprocess.run([vina_path, "--version"], capture_output=True, text=True, timeout=5)
        out = (res.stdout or res.stderr).strip()
        if "AutoDock Vina" in out:
            version_str = out.split("\n")[0]
    except Exception:
        pass

    return {
        "installed": True,
        "path": vina_path,
        "version": version_str,
        "production_ready": True
    }

def detect_openbabel() -> dict:
    obabel_path = shutil.which(config.OBABEL_EXECUTABLE)
    if not obabel_path:
        for p in ["/usr/bin/obabel", "/usr/local/bin/obabel"]:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                obabel_path = p
                break

    if not obabel_path:
        return {"installed": False, "path": None, "version": None}

    version_str = "unknown"
    try:
        res = subprocess.run([obabel_path, "-V"], capture_output=True, text=True, timeout=5)
        out = (res.stdout or res.stderr).strip()
        if "Open Babel" in out:
            version_str = out.split("\n")[0]
    except Exception:
        pass

    return {"installed": True, "path": obabel_path, "version": version_str}

def get_all_capabilities() -> dict:
    rdkit_info = detect_rdkit()
    vina_info = detect_vina()
    obabel_info = detect_openbabel()

    return {
        "worker_id": config.WORKER_ID,
        "worker_version": config.WORKER_VERSION,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
            "hostname": platform.node()
        },
        "scientific_software": {
            "rdkit": rdkit_info,
            "autodock_vina": vina_info,
            "openbabel": obabel_info
        },
        "status": "ONLINE",
        "supported_job_types": config.ALLOWED_JOB_TYPES
    }
