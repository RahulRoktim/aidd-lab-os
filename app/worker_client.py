"""
AIDD Lab OS - Worker Client (v1.4.0)
Communicates with the decoupled scientific execution service (AIDD Worker).
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Tuple

WORKER_URL = os.environ.get("AIDD_WORKER_URL", "http://127.0.0.1:8001").rstrip("/")

def _http_request(endpoint: str, method: str = "GET", data: Optional[dict] = None, timeout: float = 8.0) -> Tuple[bool, Any]:
    url = f"{WORKER_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            return True, json.loads(res_body)
    except urllib.error.HTTPError as e:
        try:
            err_json = json.loads(e.read().decode("utf-8"))
            return False, err_json.get("detail", str(e))
        except:
            return False, str(e)
    except Exception as e:
        return False, str(e)

def get_worker_status() -> dict:
    success, data = _http_request("/capabilities", timeout=2.0)
    if success:
        return {
            "connected": True,
            "worker_url": WORKER_URL,
            "worker_id": data.get("worker_id"),
            "worker_version": data.get("worker_version"),
            "platform": data.get("platform", {}),
            "scientific_software": data.get("scientific_software", {}),
            "status": "CONNECTED"
        }
    return {
        "connected": False,
        "worker_url": WORKER_URL,
        "worker_id": None,
        "worker_version": None,
        "platform": {},
        "scientific_software": {
            "rdkit": {"installed": False, "version": None, "production_ready": False},
            "autodock_vina": {"installed": False, "version": None, "production_ready": False}
        },
        "status": "DISCONNECTED",
        "error": str(data)
    }

def get_worker_readiness() -> Tuple[bool, Any]:
    return _http_request("/readiness", timeout=2.5)

def get_worker_environment() -> Tuple[bool, Any]:
    return _http_request("/environment", timeout=2.5)

def submit_descriptor_job(molecules: List[dict], experiment_id: Optional[str] = None) -> Tuple[bool, Any]:
    payload = {
        "molecules": molecules,
        "experiment_id": experiment_id
    }
    return _http_request("/jobs/descriptors", method="POST", data=payload, timeout=60.0)

def submit_standardize_job(molecules: List[dict], profile: str = "DRUG_LIKE", remove_salts: bool = True, neutralize_charges: bool = True, experiment_id: Optional[str] = None) -> Tuple[bool, Any]:
    payload = {
        "molecules": molecules,
        "profile": profile,
        "remove_salts": remove_salts,
        "neutralize_charges": neutralize_charges,
        "experiment_id": experiment_id
    }
    return _http_request("/jobs/standardize", method="POST", data=payload, timeout=60.0)

def submit_docking_job(receptor_pdbqt: str, ligands: List[dict], search_box: dict, exhaustiveness: int = 16, num_modes: int = 9, seed: int = 42, experiment_id: Optional[str] = None) -> Tuple[bool, Any]:
    payload = {
        "receptor_pdbqt": receptor_pdbqt,
        "ligands": ligands,
        "search_box": search_box,
        "exhaustiveness": exhaustiveness,
        "num_modes": num_modes,
        "seed": seed,
        "experiment_id": experiment_id
    }
    return _http_request("/jobs/docking", method="POST", data=payload, timeout=120.0)

def get_job_status(job_id: str) -> Tuple[bool, Any]:
    return _http_request(f"/jobs/{job_id}")

def cancel_job(job_id: str) -> Tuple[bool, Any]:
    return _http_request(f"/jobs/{job_id}/cancel", method="POST")

def run_worker_rdkit_validation() -> Tuple[bool, Any]:
    return _http_request("/validation/rdkit", timeout=15.0)
