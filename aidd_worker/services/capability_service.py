"""
AIDD Worker - Capability Discovery & Scientific Tool Detection
"""

import sys
import shutil
import subprocess
import platform
import os
import hashlib
import re
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
            "production_ready": False,
            "identity_verified": False,
            "binary_sha256": None,
            "version_output_sha256": None,
            "version_probe_exit_code": None,
            "detection_error": "No AutoDock Vina executable was found"
        }

    # A filename is not evidence of identity.  Treat the executable as Vina only
    # when its own successful version probe contains Vina's product banner.
    try:
        res = subprocess.run([vina_path, "--version"], capture_output=True, text=True, timeout=5)
        version_output = "\n".join(part for part in (res.stdout, res.stderr) if part).strip()
        version_line = next(
            (
                line.strip()
                for line in version_output.splitlines()
                if re.match(r"^\s*AutoDock Vina(?:\s|$)", line, flags=re.IGNORECASE)
            ),
            None,
        )
        if res.returncode != 0 or not version_line:
            return {
                "installed": False,
                "path": vina_path,
                "version": None,
                "production_ready": False,
                "identity_verified": False,
                "binary_sha256": None,
                "version_output_sha256": hashlib.sha256(version_output.encode("utf-8")).hexdigest() if version_output else None,
                "version_probe_exit_code": res.returncode,
                "detection_error": "Executable failed the AutoDock Vina --version identity probe",
            }

        digest = hashlib.sha256()
        with open(vina_path, "rb") as binary:
            for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                digest.update(chunk)
    except Exception as exc:
        return {
            "installed": False,
            "path": vina_path,
            "version": None,
            "production_ready": False,
            "identity_verified": False,
            "binary_sha256": None,
            "version_output_sha256": None,
            "version_probe_exit_code": None,
            "detection_error": f"AutoDock Vina identity probe failed: {exc}",
        }

    return {
        "installed": True,
        "path": vina_path,
        "version": version_line,
        "production_ready": True,
        "identity_verified": True,
        "binary_sha256": digest.hexdigest(),
        "version_output_sha256": hashlib.sha256(version_output.encode("utf-8")).hexdigest(),
        "version_probe_exit_code": res.returncode,
        "detection_error": None,
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
