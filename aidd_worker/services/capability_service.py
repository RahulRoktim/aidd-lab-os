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
import json
import glob
from importlib.machinery import EXTENSION_SUFFIXES
from typing import Dict, Any

from aidd_worker import config


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as binary:
        for chunk in iter(lambda: binary.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_conda_package(expected: dict) -> dict:
    pattern = os.path.join(
        sys.prefix,
        "conda-meta",
        f"{expected['name']}-{expected['version']}-{expected['build']}.json",
    )
    matches = glob.glob(pattern)
    if len(matches) != 1:
        return {"verified": False, "record_path": None, "actual": None}
    try:
        with open(matches[0], "r", encoding="utf-8") as handle:
            actual = json.load(handle)
    except (OSError, ValueError):
        return {"verified": False, "record_path": matches[0], "actual": None}
    verified = all(actual.get(field) == expected.get(field) for field in ("name", "version", "build", "url", "sha256"))
    return {
        "verified": verified,
        "record_path": os.path.realpath(matches[0]),
        "actual": {field: actual.get(field) for field in ("name", "version", "build", "url", "sha256")},
    }


def _load_rdkit_modules() -> dict:
    import rdkit
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors, rdchem
    return {
        "rdkit": rdkit,
        "Chem": Chem,
        "Descriptors": Descriptors,
        "Lipinski": Lipinski,
        "rdMolDescriptors": rdMolDescriptors,
        "rdchem": rdchem,
    }


RDKIT_KNOWN_ANSWERS = (
    {
        "name": "aspirin",
        "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "formula": "C9H8O4",
        "molecular_weight": 180.159,
        "mw_tolerance": 0.02,
        "hbd": 1,
        "hba": 3,
        "logp": 1.3101,
        "logp_tolerance": 0.03,
        "hba_api": "rdkit.Chem.Lipinski.NumHAcceptors",
    },
    {
        "name": "caffeine",
        "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
        "formula": "C8H10N4O2",
        "molecular_weight": 194.194,
        "mw_tolerance": 0.02,
        "hbd": 0,
        "hba": 6,
        "logp": -1.0293,
        "logp_tolerance": 0.03,
        "hba_api": "rdkit.Chem.Lipinski.NumHAcceptors",
    },
)


def _run_rdkit_known_answers(modules: dict) -> dict:
    evidence = []
    all_passed = True
    for expected in RDKIT_KNOWN_ANSWERS:
        molecule = modules["Chem"].MolFromSmiles(expected["smiles"])
        if molecule is None:
            evidence.append({"name": expected["name"], "passed": False, "error": "MolFromSmiles returned None"})
            all_passed = False
            continue
        actual = {
            "formula": modules["rdMolDescriptors"].CalcMolFormula(molecule),
            "molecular_weight": float(modules["Descriptors"].MolWt(molecule)),
            "hbd": int(modules["Lipinski"].NumHDonors(molecule)),
            "hba": int(modules["Lipinski"].NumHAcceptors(molecule)),
            "logp": float(modules["Descriptors"].MolLogP(molecule)),
        }
        checks = {
            "formula": actual["formula"] == expected["formula"],
            "molecular_weight": abs(actual["molecular_weight"] - expected["molecular_weight"]) <= expected["mw_tolerance"],
            "hbd": actual["hbd"] == expected["hbd"],
            "hba": actual["hba"] == expected["hba"],
            "logp": abs(actual["logp"] - expected["logp"]) <= expected["logp_tolerance"],
        }
        passed = all(checks.values())
        all_passed = all_passed and passed
        evidence.append({
            "name": expected["name"],
            "smiles": expected["smiles"],
            "passed": passed,
            "actual": actual,
            "expected": {key: expected[key] for key in ("formula", "molecular_weight", "mw_tolerance", "hbd", "hba", "logp", "logp_tolerance", "hba_api")},
            "checks": checks,
        })
    return {"passed": all_passed, "compounds": evidence}

def detect_rdkit() -> dict:
    try:
        modules = _load_rdkit_modules()
        rdkit = modules["rdkit"]
        release = config.RELEASE_ATTESTATION["rdkit"]
        module_path = os.path.realpath(rdkit.__file__)
        expected_prefix = os.path.realpath(release["expected_module_prefix"])
        compiled_paths = [
            os.path.realpath(modules["rdchem"].__file__),
            os.path.realpath(modules["rdMolDescriptors"].__file__),
        ]
        native_components_verified = all(
            os.path.isfile(path) and any(path.endswith(suffix) for suffix in EXTENSION_SUFFIXES)
            for path in compiled_paths
        )
        module_origin_verified = module_path == expected_prefix + os.sep + "__init__.py" or module_path.startswith(expected_prefix + os.sep)
        package_evidence = _verify_conda_package(release["package"])
        known_answers = _run_rdkit_known_answers(modules)
        version = getattr(rdkit, "__version__", "unknown")
        production_ready = bool(
            version == release["expected_version"]
            and module_origin_verified
            and native_components_verified
            and package_evidence["verified"]
            and known_answers["passed"]
        )
        return {
            "installed": True,
            "version": version,
            "expected_version": release["expected_version"],
            "production_ready": production_ready,
            "backend": "C++ Native Extension" if native_components_verified else "Unverified Python module",
            "module_path": module_path,
            "expected_module_prefix": expected_prefix,
            "module_origin_verified": module_origin_verified,
            "compiled_component_paths": compiled_paths,
            "native_components_verified": native_components_verified,
            "package_metadata_verified": package_evidence["verified"],
            "package_evidence": package_evidence,
            "known_answer_verified": known_answers["passed"],
            "known_answer_results": known_answers["compounds"],
            "detection_error": None if production_ready else "RDKit native/package/known-answer attestation failed",
            "features": ["SMILES", "Descriptors", "Lipinski", "QED", "Fingerprints", "2D Depiction", "Standardizer"]
        }
    except Exception as exc:
        return {
            "installed": False,
            "version": None,
            "production_ready": False,
            "backend": "Pure-Python Reference Engine (Non-Production Fallback)",
            "module_path": None,
            "module_origin_verified": False,
            "compiled_component_paths": [],
            "native_components_verified": False,
            "package_metadata_verified": False,
            "known_answer_verified": False,
            "known_answer_results": [],
            "detection_error": str(exc),
            "features": ["Reference SMILES Parser", "Calibrated Descriptors"]
        }

def detect_vina() -> dict:
    release = config.RELEASE_ATTESTATION["vina"]
    expected_path = os.path.realpath(release["expected_path"])
    expected_digest = release["expected_binary_sha256"]
    vina_path = shutil.which(config.VINA_EXECUTABLE)

    if not vina_path:
        return {
            "installed": False,
            "path": None,
            "expected_path": expected_path,
            "version": None,
            "expected_version": release["expected_version"],
            "production_ready": False,
            "identity_verified": False,
            "binary_sha256": None,
            "expected_binary_sha256": expected_digest,
            "binary_digest_verified": False,
            "path_verified": False,
            "package_metadata_verified": False,
            "version_output_sha256": None,
            "version_probe_exit_code": None,
            "detection_error": "Configured AutoDock Vina candidate was not found"
        }

    actual_path = os.path.realpath(vina_path)
    try:
        actual_digest = _file_sha256(actual_path)
        path_verified = actual_path == expected_path
        digest_verified = actual_digest == expected_digest
        package_evidence = _verify_conda_package(release["package"])
        if not (path_verified and digest_verified and package_evidence["verified"]):
            return {
                "installed": True,
                "path": actual_path,
                "expected_path": expected_path,
                "version": None,
                "expected_version": release["expected_version"],
                "production_ready": False,
                "identity_verified": False,
                "binary_sha256": actual_digest,
                "expected_binary_sha256": expected_digest,
                "binary_digest_verified": digest_verified,
                "path_verified": path_verified,
                "package_metadata_verified": package_evidence["verified"],
                "package_evidence": package_evidence,
                "version_output_sha256": None,
                "version_probe_exit_code": None,
                "detection_error": "Configured executable does not match the trusted Vina release path, binary digest, and package metadata",
            }

        # Only execute the version probe after the external digest trust check;
        # an untrusted candidate is never run merely to ask what it claims to be.
        res = subprocess.run([actual_path, "--version"], capture_output=True, text=True, timeout=5)
        version_output = "\n".join(part for part in (res.stdout, res.stderr) if part).strip()
        version_line = next(
            (
                line.strip()
                for line in version_output.splitlines()
                if re.match(r"^\s*AutoDock Vina(?:\s|$)", line, flags=re.IGNORECASE)
            ),
            None,
        )
        version_verified = version_line == release["expected_version"]
        if res.returncode != 0 or not version_line or not version_verified:
            return {
                "installed": True,
                "path": actual_path,
                "expected_path": expected_path,
                "version": None,
                "expected_version": release["expected_version"],
                "production_ready": False,
                "identity_verified": False,
                "binary_sha256": actual_digest,
                "expected_binary_sha256": expected_digest,
                "binary_digest_verified": digest_verified,
                "path_verified": path_verified,
                "package_metadata_verified": package_evidence["verified"],
                "package_evidence": package_evidence,
                "version_output_sha256": hashlib.sha256(version_output.encode("utf-8")).hexdigest() if version_output else None,
                "version_probe_exit_code": res.returncode,
                "detection_error": "Trusted binary failed the exact AutoDock Vina release version probe",
            }
    except Exception as exc:
        return {
            "installed": False,
            "path": actual_path,
            "expected_path": expected_path,
            "version": None,
            "expected_version": release["expected_version"],
            "production_ready": False,
            "identity_verified": False,
            "binary_sha256": None,
            "expected_binary_sha256": expected_digest,
            "binary_digest_verified": False,
            "path_verified": False,
            "package_metadata_verified": False,
            "version_output_sha256": None,
            "version_probe_exit_code": None,
            "detection_error": f"AutoDock Vina identity probe failed: {exc}",
        }

    return {
        "installed": True,
        "path": actual_path,
        "expected_path": expected_path,
        "version": version_line,
        "expected_version": release["expected_version"],
        "production_ready": True,
        "identity_verified": True,
        "binary_sha256": actual_digest,
        "expected_binary_sha256": expected_digest,
        "binary_digest_verified": True,
        "path_verified": True,
        "package_metadata_verified": True,
        "package_evidence": package_evidence,
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
