"""
AIDD Worker - AutoDock Vina Subprocess Execution, Input Validation & Output Parsing (v1.4.0)
"""

import os
import re
import time
import subprocess
import hashlib
import json
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from aidd_worker import config
from aidd_worker.models import DockingJobRequest, FailureRecord, ArtifactInfo
from aidd_worker.services.capability_service import detect_vina
from aidd_worker.services.artifact_service import (
    save_job_artifact,
    compute_sha256,
    resolve_job_directory,
    resolve_job_path,
)

# Synthetic receptor-shaped PDBQT fixture for plumbing tests only.  It is not a
# complete structure from PDB 4WKQ and is not scientific validation material.
EGFR_4WKQ_RECEPTOR_PDBQT = """REMARK  NAME = EGFR_4WKQ_POCKET
REMARK  ASSET_CLASS = SYNTHETIC_PLUMBING_FIXTURE
ATOM      1  N   MET A 793      22.140   1.210  51.840  1.00 20.00    -0.350 N 
ATOM      2  CA  MET A 793      22.850   0.450  52.880  1.00 20.00     0.100 C 
ATOM      3  C   MET A 793      24.320   0.880  52.950  1.00 20.00     0.550 C 
ATOM      4  O   MET A 793      24.780   1.620  52.080  1.00 20.00    -0.550 O 
ATOM      5  CB  MET A 793      22.180   0.620  54.250  1.00 20.00     0.000 C 
ATOM      6  N   CYS A 797      21.450  -2.150  54.200  1.00 20.00    -0.350 N 
ATOM      7  CA  CYS A 797      20.620  -3.210  54.780  1.00 20.00     0.100 C 
ATOM      8  CB  CYS A 797      21.100  -4.580  54.300  1.00 20.00     0.000 C 
ATOM      9  SG  CYS A 797      20.150  -5.950  55.050  1.00 20.00    -0.100 S 
ATOM     10  N   ASP A 855      25.100  -0.450  50.120  1.00 20.00    -0.350 N 
ATOM     11  CA  ASP A 855      26.240  -1.210  49.650  1.00 20.00     0.100 C 
ATOM     12  CB  ASP A 855      26.850  -0.520  48.420  1.00 20.00    -0.100 C 
ATOM     13  CG  ASP A 855      27.980  -1.320  47.810  1.00 20.00     0.700 C 
ATOM     14  OD1 ASP A 855      28.520  -2.250  48.450  1.00 20.00    -0.800 OA
ATOM     15  OD2 ASP A 855      28.320  -1.020  46.650  1.00 20.00    -0.800 OA
TER
"""

# Synthetic ligand-shaped PDBQT fixture for plumbing tests only.
SYNTHETIC_LIGAND_FIXTURE_B_PDBQT = """REMARK  NAME = SYNTHETIC_LIGAND_FIXTURE_B
REMARK  ASSET_CLASS = SYNTHETIC_PLUMBING_FIXTURE; NOT A PREPARED DRUG STRUCTURE
ROOT
ATOM      1  C1  UNL     1      22.450   0.620  52.150  1.00  0.00     0.050 C 
ATOM      2  C2  UNL     1      23.120   1.750  52.650  1.00  0.00     0.120 A 
ATOM      3  N3  UNL     1      24.420   1.850  52.350  1.00  0.00    -0.350 NA
ATOM      4  C4  UNL     1      25.120   0.820  51.520  1.00  0.00     0.380 A 
ATOM      5  C5  UNL     1      24.450  -0.350  51.020  1.00  0.00    -0.050 A 
ATOM      6  N6  UNL     1      23.150  -0.450  51.350  1.00  0.00    -0.350 NA
ATOM      7  N7  UNL     1      26.450   0.920  51.150  1.00  0.00    -0.420 N 
ATOM      8  C8  UNL     1      27.250  -0.150  50.620  1.00  0.00     0.150 A 
ENDROOT
TORSDOF 4
"""

# Synthetic receptor-shaped fixture; not a complete 1HSG structure.
HIV_1HSG_RECEPTOR_PDBQT = """REMARK  NAME = HIV1_Protease_1HSG
REMARK  ASSET_CLASS = SYNTHETIC_PLUMBING_FIXTURE
ATOM      1  N   ASP A  25      16.520  24.850   3.920  1.00 15.00    -0.350 N 
ATOM      2  CA  ASP A  25      15.820  25.650   4.950  1.00 15.00     0.100 C 
ATOM      3  CG  ASP A  25      15.120  24.750   6.020  1.00 15.00     0.700 C 
ATOM      4  OD1 ASP A  25      15.650  23.680   6.350  1.00 15.00    -0.800 OA
ATOM      5  OD2 ASP A  25      13.980  25.100   6.520  1.00 15.00    -0.800 OA
TER
"""

VINA_STANDARD_LOG_FIXTURE = """
#################################################################
# AutoDock Vina v1.2.5                                          #
#                                                               #
# Authors: Dr. Oleg Trott, The Scripps Research Institute       #
#################################################################

Reading input ... done.
Setting up the grid ... done.
Grid center: 22.4 0.8 52.5
Grid size: 20 20 20
Grid spacing: 0.375
Exhaustiveness: 16
CPU: 0
Seed: 42
Performing search ... done.
Refining results ... done.

mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1        -10.4      0.000      0.000
   2         -9.8      1.423      2.105
   3         -9.2      2.115      3.450
   4         -8.7      2.650      4.120
   5         -8.4      3.210      5.012
   6         -8.1      3.890      5.890
   7         -7.9      4.120      6.230
   8         -7.6      4.560      6.890
   9         -7.4      5.120      7.450
Writing output ... done.
Complete.
"""

def validate_pdbqt_format(content: str, filename_hint: str = "Structure") -> Tuple[bool, Optional[str]]:
    """
    Strict scientific validation of PDBQT input formatting.
    Prevents empty files, random strings, and malformed files from executing.
    """
    if not content or not content.strip():
        return False, f"{filename_hint} is empty"

    lines = content.strip().splitlines()
    has_atom_records = any(line.startswith("ATOM") or line.startswith("HETATM") for line in lines)
    if not has_atom_records:
        return False, f"{filename_hint} has no ATOM or HETATM coordinate records"

    poses, parse_error = parse_pdbqt_atom_poses(content)
    if parse_error or not poses or not poses[0]:
        return False, parse_error or f"{filename_hint} contains malformed ATOM lines without finite 3D coordinates"

    return True, None


def parse_pdbqt_atom_poses(content: str) -> Tuple[List[List[Dict[str, Any]]], Optional[str]]:
    """Parse ordered PDBQT atom identities and finite coordinates per MODEL."""
    poses: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    has_models = False
    for line_number, line in enumerate((content or "").splitlines(), start=1):
        record = line[:6].strip().upper()
        if record == "MODEL":
            has_models = True
            if current:
                poses.append(current)
                current = []
            continue
        if record == "ENDMDL":
            if current:
                poses.append(current)
                current = []
            continue
        if record not in {"ATOM", "HETATM"}:
            continue
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (TypeError, ValueError):
            return [], f"Malformed PDBQT coordinates at line {line_number}"
        if not all(math.isfinite(value) for value in (x, y, z)):
            return [], f"Non-finite PDBQT coordinates at line {line_number}"
        fields = line.split()
        if not fields:
            return [], f"Malformed PDBQT atom record at line {line_number}"
        current.append({
            "atom_name": line[12:16].strip(),
            "atom_type": fields[-1].upper(),
            "x": x,
            "y": y,
            "z": z,
        })
    if current:
        poses.append(current)
    if has_models and not poses:
        return [], "PDBQT MODEL records contained no atoms"
    return poses, None


def verify_ligand_output_integrity(
    submitted_ligand: str,
    output_pdbqt: str,
    search_box: Any,
    expected_pose_count: int,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    submitted_poses, submitted_error = parse_pdbqt_atom_poses(submitted_ligand)
    output_poses, output_error = parse_pdbqt_atom_poses(output_pdbqt)
    if submitted_error or not submitted_poses:
        return False, {}, submitted_error or "Submitted ligand contains no atoms"
    if output_error or not output_poses:
        return False, {}, output_error or "Output contains no atom-bearing poses"

    submitted_atoms = submitted_poses[0]
    submitted_identity = [(atom["atom_name"], atom["atom_type"]) for atom in submitted_atoms]
    identity_hash = _sha256_text(json.dumps(submitted_identity, separators=(",", ":")))
    pose_counts = []
    centroids = []
    margin = 5.0
    for pose_index, atoms in enumerate(output_poses, start=1):
        pose_counts.append(len(atoms))
        output_identity = [(atom["atom_name"], atom["atom_type"]) for atom in atoms]
        if output_identity != submitted_identity:
            return False, {
                "submitted_atom_count": len(submitted_atoms),
                "output_pose_atom_counts": pose_counts,
                "submitted_atom_identity_sha256": identity_hash,
            }, f"Output pose {pose_index} atom count/type/name sequence does not match the submitted ligand"
        centroid = {
            axis: sum(atom[axis] for atom in atoms) / len(atoms)
            for axis in ("x", "y", "z")
        }
        centroids.append(centroid)
        for axis in ("x", "y", "z"):
            center = float(getattr(search_box, f"center_{axis}"))
            half_size = float(getattr(search_box, f"size_{axis}")) / 2.0
            if abs(centroid[axis] - center) > half_size + margin:
                return False, {
                    "submitted_atom_count": len(submitted_atoms),
                    "output_pose_atom_counts": pose_counts,
                    "submitted_atom_identity_sha256": identity_hash,
                    "pose_centroids": centroids,
                }, f"Output pose {pose_index} centroid falls outside the requested search region plus {margin} Å integrity margin"

    if len(output_poses) != expected_pose_count:
        return False, {
            "submitted_atom_count": len(submitted_atoms),
            "output_pose_atom_counts": pose_counts,
            "submitted_atom_identity_sha256": identity_hash,
            "pose_centroids": centroids,
        }, f"Output PDBQT pose count {len(output_poses)} does not match parsed Vina table count {expected_pose_count}"

    return True, {
        "submitted_atom_count": len(submitted_atoms),
        "output_pose_atom_counts": pose_counts,
        "submitted_atom_identity_sha256": identity_hash,
        "pose_centroids": centroids,
        "search_region_integrity_margin_angstrom": margin,
        "verified": True,
    }, None

def parse_vina_log_output(log_text: str) -> List[Dict[str, Any]]:
    poses = []
    lines = log_text.splitlines()
    in_table = False
    
    for line in lines:
        line_clean = line.strip()
        if "mode |" in line or "-----+------------+" in line:
            in_table = True
            continue
        
        if in_table:
            if not line_clean or line_clean.startswith("Writing") or line_clean.startswith("Complete"):
                in_table = False
                continue
            
            parts = line_clean.split()
            if len(parts) >= 4:
                try:
                    mode = int(parts[0])
                    affinity = float(parts[1])
                    rmsd_lb = float(parts[2])
                    rmsd_ub = float(parts[3])
                    poses.append({
                        "rank": mode,
                        "affinity_kcal_mol": affinity,
                        "rmsd_lower_bound": rmsd_lb,
                        "rmsd_upper_bound": rmsd_ub
                    })
                except ValueError:
                    pass
                    
    return poses


def has_recognizable_vina_output(text: str) -> bool:
    """Require Vina's banner as well as a result table before attestation."""
    return bool(
        re.search(r"(?im)^\s*#?\s*AutoDock Vina(?:\s|$)", text or "")
        and re.search(r"(?im)^\s*mode\s*\|\s*affinity\s*\|", text or "")
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def execute_docking_job(job_id: str, request: DockingJobRequest) -> Tuple[List[Dict[str, Any]], List[FailureRecord], List[ArtifactInfo], Dict[str, Any]]:
    vina_info = detect_vina()
    job_dir = resolve_job_directory(job_id, create=True)

    artifacts = []
    failures = []
    results = []

    # 1. Validate Receptor PDBQT
    rec_valid, rec_err = validate_pdbqt_format(request.receptor_pdbqt, filename_hint="Receptor PDBQT")
    if not rec_valid:
        raise ValueError(f"Receptor validation failed: {rec_err}")

    # 2. Validate Search Box
    sb = request.search_box
    if sb.size_x <= 0 or sb.size_y <= 0 or sb.size_z <= 0:
        raise ValueError(f"Invalid search box dimensions: ({sb.size_x}, {sb.size_y}, {sb.size_z}). All sizes must be positive (> 0 Å).")

    # 3. Save Receptor PDBQT
    rec_path = resolve_job_path(job_id, "receptor.pdbqt")
    with open(rec_path, "w", encoding="utf-8") as f:
        f.write(request.receptor_pdbqt.strip())
    rec_art = save_job_artifact(job_id, "receptor.pdbqt", request.receptor_pdbqt, file_type="pdbqt")
    artifacts.append(rec_art)

    start_time = time.time()
    total_stdout = []
    total_stderr = []
    native_exit_codes: List[int] = []

    for lig in request.ligands:
        lig_id = lig.get("id") or "LIG-001"
        lig_name = lig.get("name") or lig_id
        lig_content = lig.get("pdbqt") or lig.get("smiles") or ""

        # Validate ligand
        lig_valid, lig_err = validate_pdbqt_format(lig_content, filename_hint=f"Ligand {lig_id}")
        if not lig_valid:
            failures.append(FailureRecord(
                molecule_id=lig_id,
                molecule_name=lig_name,
                smiles=lig.get("smiles", ""),
                error_type="InvalidLigandPDBQT",
                error_message=lig_err or "Malformed ligand PDBQT"
            ))
            continue

        lig_filename = f"{lig_id}.pdbqt"
        lig_path = resolve_job_path(job_id, lig_filename)
        with open(lig_path, "w", encoding="utf-8") as f:
            f.write(lig_content.strip())
        lig_art = save_job_artifact(job_id, lig_filename, lig_content, file_type="pdbqt")
        artifacts.append(lig_art)

        out_pdbqt_filename = f"{lig_id}_out.pdbqt"
        out_pdbqt_path = resolve_job_path(job_id, out_pdbqt_filename)
        log_filename = f"{lig_id}_vina.log"
        log_path = resolve_job_path(job_id, log_filename)

        config_lines = [
            f"receptor = {rec_path}",
            f"ligand = {lig_path}",
            f"center_x = {sb.center_x}",
            f"center_y = {sb.center_y}",
            f"center_z = {sb.center_z}",
            f"size_x = {sb.size_x}",
            f"size_y = {sb.size_y}",
            f"size_z = {sb.size_z}",
            f"exhaustiveness = {request.exhaustiveness or 16}",
            f"num_modes = {request.num_modes or 9}",
            f"energy_range = {request.energy_range or 3.0}",
            f"seed = {request.seed or 42}",
            f"out = {out_pdbqt_path}",
        ]
        config_text = "\n".join(config_lines) + "\n"
        config_path = resolve_job_path(job_id, f"{lig_id}_config.txt")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_text)
        conf_art = save_job_artifact(job_id, f"{lig_id}_config.txt", config_text, file_type="config")
        artifacts.append(conf_art)

        if vina_info.get("installed") and vina_info.get("identity_verified"):
            # Real subprocess invocation
            try:
                # A prior file in a reused job directory is never evidence that
                # the current subprocess created output.
                for stale_path in (out_pdbqt_path, log_path):
                    if os.path.exists(stale_path):
                        os.remove(stale_path)
                execution_vina = detect_vina()
                if not (
                    execution_vina.get("identity_verified")
                    and execution_vina.get("binary_digest_verified")
                    and execution_vina.get("path_verified")
                    and execution_vina.get("package_metadata_verified")
                ):
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaBinaryAttestationFailed",
                        error_message=execution_vina.get("detection_error") or "Vina failed release attestation immediately before execution",
                    ))
                    vina_info = execution_vina
                    continue
                vina_info = execution_vina
                execution_started_ns = time.time_ns()
                cmd = [vina_info["path"], "--config", config_path]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=config.MAX_DOCKING_TIMEOUT_SECONDS)
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                native_exit_codes.append(proc.returncode)
                total_stdout.append(f"[{lig_id} STDOUT]\n{stdout}")
                if stderr:
                    total_stderr.append(f"[{lig_id} STDERR]\n{stderr}")

                if proc.returncode != 0:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaProcessNonZeroExit",
                        error_message=f"AutoDock Vina process failed with exit code {proc.returncode}: {stderr[:200]}"
                    ))
                    continue

                log_content = stdout
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        log_content = f.read()

                if not has_recognizable_vina_output(log_content):
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaIdentityOrOutputError",
                        error_message="Process exited successfully but did not emit a recognizable AutoDock Vina banner and result table"
                    ))
                    continue

                poses = parse_vina_log_output(log_content)
                if not poses:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaOutputParseError",
                        error_message="Vina ran successfully but no poses could be parsed"
                    ))
                    continue

                if not os.path.isfile(out_pdbqt_path) or os.path.getsize(out_pdbqt_path) == 0:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaOutputFileMissing",
                        error_message="AutoDock Vina did not create a non-empty output PDBQT file"
                    ))
                    continue

                output_stat = os.stat(out_pdbqt_path)
                output_created_after_start = output_stat.st_mtime_ns >= execution_started_ns
                output_path_verified = Path(out_pdbqt_path).resolve().parent == Path(job_dir).resolve()
                if not output_created_after_start or not output_path_verified:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaOutputSandboxOrTimestampError",
                        error_message="Output PDBQT was not freshly created inside the current job sandbox",
                    ))
                    continue

                with open(out_pdbqt_path, "rb") as output_file:
                    output_bytes = output_file.read()
                output_text = output_bytes.decode("utf-8", errors="replace")
                output_valid, output_error = validate_pdbqt_format(
                    output_text,
                    filename_hint=f"Vina output for {lig_id}",
                )
                if not output_valid:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaOutputFileInvalid",
                        error_message=output_error or "AutoDock Vina output PDBQT is malformed"
                    ))
                    continue

                integrity_ok, integrity_evidence, integrity_error = verify_ligand_output_integrity(
                    lig_content,
                    output_text,
                    sb,
                    expected_pose_count=len(poses),
                )
                if not integrity_ok:
                    failures.append(FailureRecord(
                        molecule_id=lig_id,
                        molecule_name=lig_name,
                        smiles=lig.get("smiles", ""),
                        error_type="VinaLigandOutputIntegrityError",
                        error_message=integrity_error or "Output PDBQT is not identity-compatible with the submitted ligand",
                    ))
                    continue

                out_art = save_job_artifact(job_id, out_pdbqt_filename, output_bytes, file_type="pdbqt_output")
                artifacts.append(out_art)

                best_pose = poses[0]
                results.append({
                    "molecule_id": lig_id,
                    "molecule_name": lig_name,
                    "prepared_ligand_id": lig_id,
                    "prepared_ligand_name": lig_name,
                    "docking_score": best_pose["affinity_kcal_mol"],
                    "best_affinity_kcal_mol": best_pose["affinity_kcal_mol"],
                    "poses_count": len(poses),
                    "poses": poses,
                    "receptor_hash": rec_art.sha256_hash,
                    "ligand_hash": lig_art.sha256_hash,
                    "output_pdbqt_hash": out_art.sha256_hash,
                    "stdout_sha256": _sha256_text(stdout),
                    "config_sha256": conf_art.sha256_hash,
                    "tool": "AutoDock Vina",
                    "tool_version": vina_info["version"],
                    "vina_binary_sha256": vina_info["binary_sha256"],
                    "vina_expected_binary_sha256": vina_info["expected_binary_sha256"],
                    "vina_binary_digest_verified": vina_info["binary_digest_verified"],
                    "vina_path": vina_info["path"],
                    "vina_path_verified": vina_info["path_verified"],
                    "vina_package_metadata_verified": vina_info["package_metadata_verified"],
                    "output_created_after_start": output_created_after_start,
                    "output_path_verified": output_path_verified,
                    "ligand_output_integrity": integrity_evidence,
                    "result_origin": "COMPUTED"
                })

            except subprocess.TimeoutExpired:
                failures.append(FailureRecord(
                    molecule_id=lig_id,
                    molecule_name=lig_name,
                    smiles=lig.get("smiles", ""),
                    error_type="VinaTimeoutExpired",
                    error_message=f"Execution exceeded timeout limit of {config.MAX_DOCKING_TIMEOUT_SECONDS}s"
                ))
            except Exception as e:
                failures.append(FailureRecord(
                    molecule_id=lig_id,
                    molecule_name=lig_name,
                    smiles=lig.get("smiles", ""),
                    error_type="VinaSubprocessException",
                    error_message=str(e)
                ))
        else:
            # Native Vina binary not present on worker host
            # Return explicit notice
            if request.execution_mode == "NATIVE":
                failures.append(FailureRecord(
                    molecule_id=lig_id,
                    molecule_name=lig_name,
                    smiles=lig.get("smiles", ""),
                    error_type="VinaBinaryUnavailable",
                    error_message=vina_info.get("detection_error") or "AutoDock Vina failed trusted release attestation."
                ))
            else:
                # Demo fallback execution
                poses = parse_vina_log_output(VINA_STANDARD_LOG_FIXTURE)
                score_bucket = int(hashlib.sha256(lig_id.encode("utf-8")).hexdigest()[:8], 16) % 20
                base_score = -9.2 + (score_bucket / 10.0)
                for p in poses:
                    p["affinity_kcal_mol"] = round(base_score + (p["rank"] - 1) * 0.4, 1)

                results.append({
                    "molecule_id": lig_id,
                    "molecule_name": lig_name,
                    "docking_score": poses[0]["affinity_kcal_mol"],
                    "best_affinity_kcal_mol": poses[0]["affinity_kcal_mol"],
                    "poses_count": len(poses),
                    "poses": poses,
                    "receptor_hash": rec_art.sha256_hash,
                    "ligand_hash": lig_art.sha256_hash,
                    "tool": "AIDD Vina-table demo fixture",
                    "tool_version": "demo-fixture-v1",
                    "result_origin": "DEMO"
                })
                total_stdout.append(f"[{lig_id} NOTICE] Native AutoDock Vina was unavailable. Output came from a synthetic demo fixture and is not native evidence.")

    # Preserve a real native failure code if any subprocess failed.  A zero is
    # only valid when every attempted native subprocess produced a parsed
    # computed result and the job has no failure records.  Demo/fallback runs,
    # timeouts, parse failures, and other incomplete executions remain None.
    aggregate_exit_code = next((code for code in native_exit_codes if code != 0), None)
    if (
        aggregate_exit_code is None
        and native_exit_codes
        and not failures
        and len(results) == len(native_exit_codes)
        and all(result.get("result_origin") == "COMPUTED" for result in results)
    ):
        aggregate_exit_code = 0

    duration = round(time.time() - start_time, 3)
    stdout_text = "\n".join(total_stdout)
    stderr_text = "\n".join(total_stderr)
    meta = {
        "tool": "AutoDock Vina" if vina_info.get("identity_verified") else "AIDD Vina-table demo fixture",
        "tool_version": vina_info.get("version") or "demo-fixture-v1",
        "vina_binary_sha256": vina_info.get("binary_sha256"),
        "vina_expected_binary_sha256": vina_info.get("expected_binary_sha256"),
        "vina_binary_digest_verified": vina_info.get("binary_digest_verified", False),
        "vina_path": vina_info.get("path"),
        "vina_expected_path": vina_info.get("expected_path"),
        "vina_path_verified": vina_info.get("path_verified", False),
        "vina_package_metadata_verified": vina_info.get("package_metadata_verified", False),
        "vina_version_output_sha256": vina_info.get("version_output_sha256"),
        "vina_identity_verified": bool(vina_info.get("identity_verified")),
        "production_ready": bool(vina_info.get("installed") and vina_info.get("identity_verified")),
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_sha256": _sha256_text(stdout_text) if stdout_text else None,
        "stderr_sha256": _sha256_text(stderr_text) if stderr_text else None,
        "receptor_sha256": rec_art.sha256_hash,
        "output_pdbqt_hashes": [r.get("output_pdbqt_hash") for r in results if r.get("output_pdbqt_hash")],
        "prepared_ligand_attestations": [
            {
                "prepared_ligand_id": result.get("prepared_ligand_id"),
                "prepared_ligand_name": result.get("prepared_ligand_name"),
                "ligand_hash": result.get("ligand_hash"),
                "output_pdbqt_hash": result.get("output_pdbqt_hash"),
                "ligand_output_integrity": result.get("ligand_output_integrity"),
            }
            for result in results
        ],
        "duration_seconds": duration,
        "search_box": sb.dict(),
        "exhaustiveness": request.exhaustiveness or 16,
        "seed": request.seed or 42,
        "exit_code": aggregate_exit_code
    }
    reproducibility_payload = {
        "tool": meta["tool"],
        "tool_version": meta["tool_version"],
        "vina_binary_sha256": meta["vina_binary_sha256"],
        "search_box": meta["search_box"],
        "exhaustiveness": meta["exhaustiveness"],
        "num_modes": request.num_modes or 9,
        "energy_range": request.energy_range or 3.0,
        "seed": meta["seed"],
        "results": [
            {
                "molecule_id": result.get("molecule_id"),
                "docking_score": result.get("docking_score"),
                "poses": result.get("poses"),
                "result_origin": result.get("result_origin"),
                "receptor_hash": result.get("receptor_hash"),
                "ligand_hash": result.get("ligand_hash"),
                "output_pdbqt_hash": result.get("output_pdbqt_hash"),
            }
            for result in sorted(results, key=lambda item: item.get("molecule_id") or "")
        ],
    }
    meta["reproducibility_hash"] = _sha256_text(json.dumps(reproducibility_payload, sort_keys=True, separators=(",", ":")))

    return results, failures, artifacts, meta

# Backward compatibility alias
VINA_FIXTURE_LOG = VINA_STANDARD_LOG_FIXTURE
