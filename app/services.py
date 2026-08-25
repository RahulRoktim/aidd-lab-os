from app import worker_client
"""
AIDD Lab OS - Scientific Service Layer
Handles molecule standardization, descriptor computation, immutable dataset lineage,
AutoDock Vina docking import, ADMET data import, transparent candidate ranking,
SHA-256 artifact hashing, experiment reproduction, and reproducibility bundle generation.
"""

import os
import io
import csv
import json
import uuid
import time
import math
import zipfile
import hashlib
import platform
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.database import get_db, get_db_connection
from app.scientific_engine import ScientificEngine

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def compute_sha256(data: str or bytes) -> str:
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def get_system_environment_info() -> dict:
    engine_status = ScientificEngine.get_engine_status()
    worker_st = worker_client.get_worker_status()
    has_native_rdk = engine_status["has_rdkit"] or (worker_st["connected"] and worker_st.get("scientific_software", {}).get("rdkit", {}).get("installed", False))
    vina_capability = worker_st.get("scientific_software", {}).get("autodock_vina", {})
    has_native_vina = bool(
        worker_st["connected"]
        and vina_capability.get("installed")
        and vina_capability.get("identity_verified")
        and vina_capability.get("production_ready")
    )

    mode = "NATIVE" if (has_native_rdk and has_native_vina) else ("IMPORT_ONLY" if not worker_st["connected"] else "DEMO_FALLBACK")

    env_dict = {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "runtime": "AIDD Lab OS Scientific Runtime v1.4.0",
        "execution_mode": mode,
        "cheminformatics_engine": "RDKit Native (C++)" if has_native_rdk else "AIDD Python Reference Engine (Non-Production Fallback)",
        "has_native_rdkit": has_native_rdk,
        "rdkit_version": engine_status["rdkit_version"] or (worker_st.get("scientific_software", {}).get("rdkit", {}).get("version")),
        "has_native_vina": has_native_vina,
        "vina_version": worker_st.get("scientific_software", {}).get("autodock_vina", {}).get("version"),
        "engine_notice": "Running in pure-Python reference mode; descriptor results are simulated estimates." if not has_native_rdk else "Native RDKit C++ kernel active.",
        "scientific_worker": {
            "connected": worker_st["connected"],
            "worker_id": worker_st.get("worker_id"),
            "worker_url": worker_st.get("worker_url"),
            "status": worker_st["status"],
            "capabilities": worker_st.get("scientific_software", {})
        },
        "hardware": platform.machine()
    }
    env_dict["environment_sha256"] = hashlib.sha256(json.dumps(env_dict, sort_keys=True).encode('utf-8')).hexdigest()
    return env_dict

# -------------------------------------------------------------------
# PROJECTS
# -------------------------------------------------------------------

def create_project(name: str, description: str = "", disease_indication: str = "",
                   target_protein: str = "", hypothesis: str = "") -> dict:
    proj_id = gen_id("proj")
    ts = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, description, disease_indication, target_protein, hypothesis, current_stage, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Dataset', ?, ?)
            """,
            (proj_id, name, description, disease_indication, target_protein, hypothesis, ts, ts)
        )
    return get_project(proj_id)

def list_projects() -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM molecules m WHERE m.project_id = p.id) as molecule_count,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id) as experiment_count,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id AND e.status = 'completed') as completed_experiments,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id AND e.status = 'failed') as failed_experiments,
                   (SELECT COUNT(*) FROM datasets d WHERE d.project_id = p.id) as dataset_count,
                   (SELECT COUNT(*) FROM candidate_scores cs WHERE cs.project_id = p.id AND cs.tier IN ('Lead Candidate', 'Backup Lead')) as candidate_count
            FROM projects p
            ORDER BY p.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

def get_project(project_id: str) -> Optional[dict]:
    with get_db() as conn:
        p = conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM molecules m WHERE m.project_id = p.id) as molecule_count,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id) as experiment_count,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id AND e.status = 'completed') as completed_experiments,
                   (SELECT COUNT(*) FROM experiments e WHERE e.project_id = p.id AND e.status = 'failed') as failed_experiments,
                   (SELECT COUNT(*) FROM datasets d WHERE d.project_id = p.id) as dataset_count,
                   (SELECT COUNT(*) FROM candidate_scores cs WHERE cs.project_id = p.id AND cs.tier IN ('Lead Candidate', 'Backup Lead')) as candidate_count,
                   (SELECT COUNT(*) FROM decision_logs dl WHERE dl.project_id = p.id) as decision_count
            FROM projects p
            WHERE p.id = ?
            """,
            (project_id,)
        ).fetchone()
        if not p:
            return None
        res = dict(p)

        recent_exps = conn.execute(
            "SELECT * FROM experiments WHERE project_id = ? ORDER BY created_at DESC LIMIT 5",
            (project_id,)
        ).fetchall()
        res['recent_experiments'] = [dict(e) for e in recent_exps]

        top_cands = conn.execute(
            """
            SELECT cs.*, m.name as molecule_name, m.smiles, m.molecular_weight, m.logp, m.tpsa,
                   dr.docking_score, dr.result_origin as docking_origin,
                   ar.admet_risk_level, ar.result_origin as admet_origin
            FROM candidate_scores cs
            JOIN molecules m ON cs.molecule_id = m.id
            LEFT JOIN docking_results dr ON cs.molecule_id = dr.molecule_id AND cs.project_id = dr.project_id
            LEFT JOIN admet_results ar ON cs.molecule_id = ar.molecule_id AND cs.project_id = ar.project_id
            WHERE cs.project_id = ?
            ORDER BY cs.composite_score DESC
            LIMIT 5
            """,
            (project_id,)
        ).fetchall()
        res['top_candidates'] = [dict(c) for c in top_cands]

        return res

def delete_project(project_id: str) -> bool:
    with get_db() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return True

# -------------------------------------------------------------------
# EXPERIMENT ACCESS & DETAIL
# -------------------------------------------------------------------

def list_experiments(project_id: str) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT e.*,
                   inds.version_label as input_dataset_label,
                   outds.version_label as output_dataset_label
            FROM experiments e
            LEFT JOIN datasets inds ON e.input_dataset_id = inds.id
            LEFT JOIN datasets outds ON e.output_dataset_id = outds.id
            WHERE e.project_id = ?
            ORDER BY e.created_at DESC
            """,
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_experiment_detail(experiment_id: str) -> Optional[dict]:
    with get_db() as conn:
        exp = conn.execute(
            """
            SELECT e.*,
                   inds.version_label as input_dataset_label,
                   inds.name as input_dataset_name,
                   outds.version_label as output_dataset_label,
                   outds.name as output_dataset_name
            FROM experiments e
            LEFT JOIN datasets inds ON e.input_dataset_id = inds.id
            LEFT JOIN datasets outds ON e.output_dataset_id = outds.id
            WHERE e.id = ?
            """,
            (experiment_id,)
        ).fetchone()
        if not exp:
            return None
        res = dict(exp)

        try: res["environment_info"] = json.loads(res["environment_info"]) if res["environment_info"] else {}
        except: pass
        try: res["parameters"] = json.loads(res["parameters"]) if res["parameters"] else {}
        except: pass
        try: res["metrics"] = json.loads(res["metrics"]) if res["metrics"] else {}
        except: pass
        try: res["notes_log"] = json.loads(res["notes_log"]) if res.get("notes_log") else []
        except: pass

        failures = conn.execute(
            "SELECT * FROM experiment_failures WHERE experiment_id = ? ORDER BY created_at ASC",
            (experiment_id,)
        ).fetchall()
        res["failures"] = [dict(f) for f in failures]

        artifacts = conn.execute(
            "SELECT * FROM experiment_artifacts WHERE experiment_id = ? ORDER BY created_at ASC",
            (experiment_id,)
        ).fetchall()
        res["artifacts"] = [dict(a) for a in artifacts]

        docking_results = conn.execute(
            "SELECT * FROM docking_results WHERE experiment_id = ? ORDER BY molecule_id ASC",
            (experiment_id,)
        ).fetchall()
        res["docking_results"] = [dict(row) for row in docking_results]

        admet_results = conn.execute(
            "SELECT * FROM admet_results WHERE experiment_id = ? ORDER BY molecule_id ASC",
            (experiment_id,)
        ).fetchall()
        res["admet_results"] = [dict(row) for row in admet_results]

        upstream = conn.execute(
            "SELECT * FROM provenance_edges WHERE target_id = ? AND project_id = ?",
            (experiment_id, res["project_id"])
        ).fetchall()
        downstream = conn.execute(
            "SELECT * FROM provenance_edges WHERE source_id = ? AND project_id = ?",
            (experiment_id, res["project_id"])
        ).fetchall()
        res["provenance_upstream"] = [dict(u) for u in upstream]
        res["provenance_downstream"] = [dict(d) for d in downstream]

        return res

def export_failures_csv(experiment_id: str) -> str:
    exp = get_experiment_detail(experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["failure_id", "molecule_id", "molecule_name", "smiles", "pipeline_stage", "error_type", "error_message", "timestamp"])
    for f in exp["failures"]:
        writer.writerow([
            f["id"], f.get("molecule_id", ""), f.get("molecule_name", ""), f.get("smiles", ""),
            f["pipeline_stage"], f["error_type"], f["error_message"], f["created_at"]
        ])
    return output.getvalue()

# -------------------------------------------------------------------
# MOLECULE IMPORT & STANDARDIZATION
# -------------------------------------------------------------------

def import_molecules_from_csv_or_list(project_id: str,
                                      molecule_records: List[dict],
                                      dataset_name: Optional[str] = None,
                                      notes: str = "") -> dict:
    project = get_project(project_id)
    if not project:
        raise ValueError(f"Project not found: {project_id}")

    exp_id = gen_id("exp")
    start_ts = now_iso()
    start_time = time.time()

    successful_molecules = []
    failed_molecules = []
    raw_payload_str = json.dumps(molecule_records, sort_keys=True)
    input_hash = compute_sha256(raw_payload_str)

    seen_ids = set()

    for i, rec in enumerate(molecule_records):
        mol_id = (rec.get("id") or rec.get("molecule_id") or f"MOL-{i+1:04d}").strip()
        mol_name = (rec.get("name") or rec.get("molecule_name") or f"Compound {i+1}").strip()
        raw_smiles = (rec.get("smiles") or rec.get("SMILES") or "").strip()

        if not raw_smiles:
            failed_molecules.append({
                "molecule_id": mol_id,
                "molecule_name": mol_name,
                "smiles": "",
                "error_type": "EmptySMILES",
                "error_message": "Molecule record missing SMILES string"
            })
            continue

        if mol_id in seen_ids:
            failed_molecules.append({
                "molecule_id": mol_id,
                "molecule_name": mol_name,
                "smiles": raw_smiles,
                "error_type": "DuplicateIdentifier",
                "error_message": f"Duplicate molecule ID '{mol_id}' detected in input batch"
            })
            continue
        seen_ids.add(mol_id)

        std_res = ScientificEngine.standardize_molecule(raw_smiles, remove_salts=False)
        if not std_res["success"]:
            failed_molecules.append({
                "molecule_id": mol_id,
                "molecule_name": mol_name,
                "smiles": raw_smiles,
                "error_type": "ParsingOrValenceError",
                "error_message": std_res["error"]
            })
            continue

        standardized_smi = std_res["standardized_smiles"]
        desc = ScientificEngine.calculate_descriptors(standardized_smi)
        if not desc["valid"]:
            failed_molecules.append({
                "molecule_id": mol_id,
                "molecule_name": mol_name,
                "smiles": raw_smiles,
                "error_type": "DescriptorCalculationError",
                "error_message": desc["error"]
            })
            continue

        fp = ScientificEngine.generate_fingerprint(standardized_smi)
        svg = ScientificEngine.generate_2d_structure(standardized_smi, width=240, height=180, dark_mode=True)
        mol_hash = compute_sha256(f"{mol_id}:{raw_smiles}:{desc['canonical_smiles'] if 'canonical_smiles' in desc else standardized_smi}")

        mol_data = {
            "id": mol_id,
            "project_id": project_id,
            "name": mol_name,
            "smiles": standardized_smi,
            "original_smiles": raw_smiles,
            "standardized_smiles": standardized_smi,
            "standardization_notes": "Initial raw ingestion",
            "canonical_smiles": desc["smiles"],
            "formula": desc["formula"],
            "molecular_weight": desc["molecular_weight"],
            "exact_molecular_weight": desc.get("exact_molecular_weight", desc["molecular_weight"]),
            "logp": desc["logp"],
            "hbd": desc["hbd"],
            "hba": desc["hba"],
            "tpsa": desc["tpsa"],
            "rotatable_bonds": desc["rotatable_bonds"],
            "heavy_atoms": desc["heavy_atoms"],
            "num_rings": desc["num_rings"],
            "lipinski_violations": desc["lipinski_violations"],
            "lipinski_pass": 1 if desc["lipinski_pass"] else 0,
            "veber_pass": 1 if desc["veber_pass"] else 0,
            "qed": desc["qed"],
            "sas_score": desc["sas_score"],
            "fingerprint_bits": json.dumps(fp),
            "svg_structure": svg,
            "descriptor_origin": desc.get("result_origin") or "SIMULATED",
            "sha256_hash": mol_hash,
            "status": "active",
            "tier": "Unassigned",
            "created_at": start_ts
        }
        successful_molecules.append(mol_data)

    end_time = time.time()
    duration = round(end_time - start_time, 3)
    end_ts = now_iso()

    with get_db() as conn:
        v_row = conn.execute("SELECT MAX(version) as max_v FROM datasets WHERE project_id = ?", (project_id,)).fetchone()
        next_v = (v_row['max_v'] or 0) + 1
        ds_id = gen_id("ds")
        ds_label = f"{project['name'].replace(' ', '_')}_dataset_v{next_v}"
        d_name = dataset_name or f"Raw Ingested Library v{next_v}"
        dataset_content_hash = compute_sha256("".join([m["sha256_hash"] for m in successful_molecules]))

        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, 'Dataset', ?, ?, ?)
            """,
            (ds_id, project_id, d_name, next_v, ds_label, f"Initial import of {len(successful_molecules)} parsed molecules", len(successful_molecules), dataset_content_hash, end_ts)
        )

        for m in successful_molecules:
            conn.execute(
                """
                INSERT OR REPLACE INTO molecules
                (id, project_id, name, smiles, original_smiles, standardized_smiles, standardization_notes, canonical_smiles, formula, molecular_weight, exact_molecular_weight, logp, hbd, hba, tpsa, rotatable_bonds, heavy_atoms, num_rings, lipinski_violations, lipinski_pass, veber_pass, qed, sas_score, fingerprint_bits, svg_structure, descriptor_origin, sha256_hash, status, tier, created_at)
                VALUES (:id, :project_id, :name, :smiles, :original_smiles, :standardized_smiles, :standardization_notes, :canonical_smiles, :formula, :molecular_weight, :exact_molecular_weight, :logp, :hbd, :hba, :tpsa, :rotatable_bonds, :heavy_atoms, :num_rings, :lipinski_violations, :lipinski_pass, :veber_pass, :qed, :sas_score, :fingerprint_bits, :svg_structure, :descriptor_origin, :sha256_hash, :status, :tier, :created_at)
                """,
                m
            )
            conn.execute(
                "INSERT OR IGNORE INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)",
                (ds_id, m["id"], end_ts)
            )

        exp_status = "completed" if successful_molecules else "failed"
        engine_info = ScientificEngine.get_engine_status()
        parameters = {
            "source_type": "CSV/List Ingestion",
            "input_payload_sha256": input_hash,
            "engine": engine_info["active_engine"],
            "is_rdkit_native": engine_info["has_rdkit"],
            "calculate_descriptors": True,
            "generate_2d_structures": True,
            "notes": notes
        }
        metrics = {
            "total_submitted": len(molecule_records),
            "successful_parsed": len(successful_molecules),
            "failed_parsing": len(failed_molecules),
            "mean_mw": round(sum(m["molecular_weight"] for m in successful_molecules) / max(1, len(successful_molecules)), 2) if successful_molecules else 0.0,
            "mean_logp": round(sum(m["logp"] for m in successful_molecules) / max(1, len(successful_molecules)), 2) if successful_molecules else 0.0,
            "ro5_compliance_rate": f"{round((sum(m['lipinski_pass'] for m in successful_molecules) / max(1, len(successful_molecules))) * 100, 1)}%" if successful_molecules else "0%"
        }
        log_lines = [
            f"[{start_ts}] [INFO] Starting molecule ingestion for project '{project['name']}'",
            f"[{start_ts}] [INFO] Input payload SHA-256: {input_hash}",
            f"[{start_ts}] [INFO] Computational Engine: {engine_info['active_engine']}",
            f"[{end_ts}] [INFO] Ingested {len(successful_molecules)} valid molecules, recorded {len(failed_molecules)} failures",
            f"[{end_ts}] [INFO] Generated immutable dataset '{ds_label}' (Hash: {dataset_content_hash[:12]}...)"
        ]

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'molecule_import', ?, 'Dataset', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?, ?, ?, ?, ?, '[]', '', ?)
            """,
            (
                exp_id, project_id, f"Molecule Ingestion #{next_v}", exp_status, ds_id,
                engine_info["active_engine"], engine_info.get("rdkit_version") or "1.2.0",
                start_ts, end_ts, duration, len(molecule_records), len(successful_molecules), len(failed_molecules),
                json.dumps(get_system_environment_info()), json.dumps(parameters), json.dumps(metrics),
                "\n".join(log_lines),
                f"{len(failed_molecules)} parsing failures recorded" if failed_molecules else "",
                notes, start_ts
            )
        )

        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp_id, ds_id))

        for f in failed_molecules:
            conn.execute(
                """
                INSERT INTO experiment_failures (id, experiment_id, molecule_id, molecule_name, smiles, pipeline_stage, error_type, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, 'Dataset', ?, ?, ?)
                """,
                (gen_id("fail"), exp_id, f["molecule_id"], f["molecule_name"], f["smiles"], f["error_type"], f["error_message"], end_ts)
            )

        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'experiment', ?, 'dataset', 'generated_from', ?, ?)
            """,
            (gen_id("edge"), project_id, exp_id, ds_id, json.dumps({"action": "imported", "molecule_count": len(successful_molecules)}), end_ts)
        )

        raw_csv_text = export_dataset_csv_from_list(successful_molecules)
        csv_hash = compute_sha256(raw_csv_text)
        conn.execute(
            """
            INSERT INTO experiment_artifacts (id, experiment_id, name, file_type, file_size_bytes, sha256_hash, file_path, content_preview, created_at)
            VALUES (?, ?, ?, 'csv', ?, ?, ?, ?, ?)
            """,
            (gen_id("art"), exp_id, f"{ds_label}.csv", len(raw_csv_text.encode()), csv_hash, f"data/artifacts/{ds_label}.csv", raw_csv_text[:200], end_ts)
        )

        conn.execute("UPDATE projects SET current_stage = 'Dataset', updated_at = ? WHERE id = ?", (end_ts, project_id))

    return {
        "dataset_id": ds_id,
        "dataset_label": ds_label,
        "dataset_sha256": dataset_content_hash,
        "experiment_id": exp_id,
        "total_parsed": len(successful_molecules),
        "total_failed": len(failed_molecules),
        "failures": failed_molecules
    }

def run_standardization_experiment(project_id: str,
                                   input_dataset_id: str,
                                   profile: str = "DRUG_LIKE",
                                   experiment_name: str = "Standardization & Desalting",
                                   remove_salts: bool = True,
                                   neutralize_charges: bool = True,
                                   filter_lipinski: bool = False,
                                   max_mw: float = 650.0,
                                   max_logp: float = 6.8,
                                   notes: str = "") -> dict:
    project = get_project(project_id)
    in_ds = get_dataset_detail(input_dataset_id)
    if not project or not in_ds:
        raise ValueError("Project or input dataset not found")

    exp_id = gen_id("exp")
    start_ts = now_iso()
    start_time = time.time()

    successful_molecules = []
    failed_molecules = []

    for m in in_ds["molecules"]:
        orig_smi = m.get("original_smiles") or m["smiles"]
        std_res = ScientificEngine.standardize_molecule(orig_smi, remove_salts=remove_salts, neutralize=neutralize_charges)
        if not std_res["success"]:
            failed_molecules.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": orig_smi,
                "error_type": "StandardizationFailed",
                "error_message": std_res["error"]
            })
            continue

        clean_smi = std_res["standardized_smiles"]
        desc = ScientificEngine.calculate_descriptors(clean_smi)
        if not desc["valid"]:
            failed_molecules.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": orig_smi,
                "error_type": "DescriptorCalculationError",
                "error_message": desc["error"]
            })
            continue

        if filter_lipinski and desc["lipinski_violations"] > 1:
            failed_molecules.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": orig_smi,
                "error_type": "LipinskiViolation",
                "error_message": f"Failed Rule of 5: {', '.join(desc['lipinski_violation_details'])}"
            })
            continue

        if desc["molecular_weight"] > max_mw:
            failed_molecules.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": orig_smi,
                "error_type": "MolecularWeightCutoff",
                "error_message": f"MW ({desc['molecular_weight']} Da) exceeded cutoff of {max_mw} Da"
            })
            continue

        if desc["logp"] > max_logp:
            failed_molecules.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": orig_smi,
                "error_type": "LipophilicityCutoff",
                "error_message": f"LogP ({desc['logp']}) exceeded cutoff of {max_logp}"
            })
            continue

        mol_data = dict(m)
        mol_data["smiles"] = clean_smi
        mol_data["standardized_smiles"] = clean_smi
        mol_data["standardization_notes"] = f"Standardized via {experiment_name}. Salt stripped: {remove_salts}"
        mol_data["molecular_weight"] = desc["molecular_weight"]
        mol_data["logp"] = desc["logp"]
        mol_data["tpsa"] = desc["tpsa"]
        mol_data["hbd"] = desc["hbd"]
        mol_data["hba"] = desc["hba"]
        mol_data["rotatable_bonds"] = desc["rotatable_bonds"]
        mol_data["lipinski_violations"] = desc["lipinski_violations"]
        mol_data["lipinski_pass"] = 1 if desc["lipinski_pass"] else 0
        mol_data["qed"] = desc["qed"]
        mol_data["svg_structure"] = ScientificEngine.generate_2d_structure(clean_smi, width=240, height=180, dark_mode=True)
        mol_data["sha256_hash"] = compute_sha256(f"{m['id']}:{orig_smi}:{clean_smi}")
        successful_molecules.append(mol_data)

    end_time = time.time()
    duration = round(end_time - start_time, 3)
    end_ts = now_iso()

    with get_db() as conn:
        v_row = conn.execute("SELECT MAX(version) as max_v FROM datasets WHERE project_id = ?", (project_id,)).fetchone()
        next_v = (v_row['max_v'] or 0) + 1
        out_ds_id = gen_id("ds")
        out_ds_label = f"{project['name'].replace(' ', '_')}_dataset_v{next_v}"
        dataset_content_hash = compute_sha256("".join([m["sha256_hash"] for m in successful_molecules]))

        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'Preprocessing', ?, ?, ?)
            """,
            (
                out_ds_id, project_id, f"Standardized Dataset v{next_v}", next_v, out_ds_label,
                input_dataset_id,
                f"Standardized and filtered from {in_ds['version_label']}. Retained {len(successful_molecules)} compounds.",
                len(successful_molecules), dataset_content_hash, end_ts
            )
        )

        for sm in successful_molecules:
            conn.execute(
                """
                UPDATE molecules SET
                    smiles = :smiles,
                    standardized_smiles = :standardized_smiles,
                    standardization_notes = :standardization_notes,
                    molecular_weight = :molecular_weight,
                    logp = :logp,
                    tpsa = :tpsa,
                    hbd = :hbd,
                    hba = :hba,
                    rotatable_bonds = :rotatable_bonds,
                    lipinski_violations = :lipinski_violations,
                    lipinski_pass = :lipinski_pass,
                    qed = :qed,
                    svg_structure = :svg_structure,
                    sha256_hash = :sha256_hash
                WHERE id = :id AND project_id = :project_id
                """,
                sm
            )
            conn.execute(
                "INSERT OR IGNORE INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)",
                (out_ds_id, sm["id"], end_ts)
            )

        engine_info = ScientificEngine.get_engine_status()
        parameters = {
            "input_dataset": in_ds["version_label"],
            "remove_salts": remove_salts,
            "neutralize_charges": neutralize_charges,
            "filter_lipinski": filter_lipinski,
            "max_mw": max_mw,
            "max_logp": max_logp,
            "engine": engine_info["active_engine"],
            "notes": notes
        }
        metrics = {
            "molecules_in": len(in_ds["molecules"]),
            "molecules_out": len(successful_molecules),
            "molecules_failed": len(failed_molecules),
            "retention_rate": f"{round((len(successful_molecules) / max(1, len(in_ds['molecules']))) * 100, 1)}%"
        }
        log_lines = [
            f"[{start_ts}] [INFO] Starting Standardization Experiment '{experiment_name}'",
            f"[{start_ts}] [INFO] Input Dataset: {in_ds['version_label']} ({len(in_ds['molecules'])} molecules)",
            f"[{end_ts}] [INFO] Cleaned {len(successful_molecules)} structures, excluded {len(failed_molecules)} compounds",
            f"[{end_ts}] [INFO] Created immutable snapshot '{out_ds_label}' (Hash: {dataset_content_hash[:12]}...)"
        ]

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'preprocessing', 'completed', 'Preprocessing', ?, ?, 'AIDD Standardization Kernel', '1.2.0', ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?, ?, ?, ?, ?, '[]', '', ?)
            """,
            (
                exp_id, project_id, experiment_name, input_dataset_id, out_ds_id,
                start_ts, end_ts, duration, len(in_ds["molecules"]), len(successful_molecules), len(failed_molecules),
                json.dumps(get_system_environment_info()), json.dumps(parameters), json.dumps(metrics),
                "\n".join(log_lines),
                f"{len(failed_molecules)} excluded" if failed_molecules else "",
                notes, start_ts
            )
        )

        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp_id, out_ds_id))

        for f in failed_molecules:
            conn.execute(
                """
                INSERT INTO experiment_failures (id, experiment_id, molecule_id, molecule_name, smiles, pipeline_stage, error_type, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, 'Preprocessing', ?, ?, ?)
                """,
                (gen_id("fail"), exp_id, f["molecule_id"], f["molecule_name"], f["smiles"], f["error_type"], f["error_message"], end_ts)
            )

        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'dataset', ?, 'experiment', 'processed_by', ?, ?)
            """,
            (gen_id("edge"), project_id, input_dataset_id, exp_id, json.dumps({"action": "standardization_input"}), end_ts)
        )
        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'experiment', ?, 'dataset', 'generated_from', ?, ?)
            """,
            (gen_id("edge"), project_id, exp_id, out_ds_id, json.dumps({"action": "standardization_output", "sha256": dataset_content_hash}), end_ts)
        )

        conn.execute("UPDATE projects SET current_stage = 'Preprocessing', updated_at = ? WHERE id = ?", (end_ts, project_id))

    return {
        "experiment_id": exp_id,
        "output_dataset_id": out_ds_id,
        "output_dataset_label": out_ds_label,
        "dataset_sha256": dataset_content_hash,
        "molecules_in": len(in_ds["molecules"]),
        "molecules_out": len(successful_molecules),
        "molecules_failed": len(failed_molecules)
    }

# -------------------------------------------------------------------
# DOCKING SERVICE
# -------------------------------------------------------------------

def import_or_run_docking(project_id: str,
                          input_dataset_id: str,
                          experiment_name: str = "AutoDock Vina Screen",
                          docking_tool: str = "AutoDock Vina",
                          receptor: str = "EGFR Kinase Domain (PDB: 1M17 / 4WKQ)",
                          grid_center: str = "x=22.0, y=0.5, z=52.8",
                          grid_size: str = "20 x 20 x 20 Å",
                          center_x: float = 22.0,
                          center_y: float = 0.5,
                          center_z: float = 52.8,
                          size_x: float = 20.0,
                          size_y: float = 20.0,
                          size_z: float = 20.0,
                          exhaustiveness: int = 16,
                          seed: Optional[int] = 42,
                          result_origin: str = "IMPORTED",
                          custom_scores_csv: Optional[str] = None,
                          notes: str = "",
                          receptor_pdbqt: Optional[str] = None,
                          prepared_ligands: Optional[list] = None,
                          num_modes: int = 9) -> dict:
    project = get_project(project_id)
    in_ds = get_dataset_detail(input_dataset_id)
    if not project or not in_ds:
        raise ValueError("Project or input dataset not found")

    result_origin = (result_origin or "").upper()
    if result_origin not in {"COMPUTED", "IMPORTED", "SIMULATED", "DEMO"}:
        raise ValueError("result_origin must be one of COMPUTED, IMPORTED, SIMULATED, or DEMO")
    if result_origin == "COMPUTED" and custom_scores_csv:
        raise ValueError("COMPUTED docking cannot accept imported score data")
    if result_origin == "IMPORTED" and not custom_scores_csv:
        raise ValueError("IMPORTED docking requires custom_scores_csv; scores are never synthesized")

    exp_id = gen_id("exp")
    start_ts = now_iso()
    start_time = time.time()

    docking_data = {}

    # NEW LOGIC: Native Worker Integration
    worker_job_id = None
    worker_id = None
    worker_env_hash = None
    worker_is_native = False
    reproducibility_hash = None
    exit_code = None
    worker_error = None
    vina_binary_sha256 = None
    vina_version_output_sha256 = None
    stdout_sha256 = None
    output_pdbqt_hashes = []

    if result_origin == "IMPORTED":
        actual_tool = docking_tool or "Imported docking data"
        actual_tool_version = "imported-unspecified"
    elif result_origin == "SIMULATED":
        actual_tool = "AIDD docking descriptor heuristic"
        actual_tool_version = "simulation-v1"
    elif result_origin == "DEMO":
        actual_tool = "AIDD docking demo fixture"
        actual_tool_version = "demo-fixture-v1"
    else:
        actual_tool = "AutoDock Vina"
        actual_tool_version = "unverified"

    receptor_hash = compute_sha256(receptor_pdbqt) if receptor_pdbqt else compute_sha256(f"{receptor}:{grid_center}:{grid_size}:{exhaustiveness}")
    if result_origin == "COMPUTED":
        from app.worker_client import submit_docking_job
        if not receptor_pdbqt or not prepared_ligands:
            raise ValueError("Native execution requires explicit receptor_pdbqt and prepared_ligands in the request.")

        search_box = {
            "center_x": center_x,
            "center_y": center_y,
            "center_z": center_z,
            "size_x": size_x,
            "size_y": size_y,
            "size_z": size_z
        }

        succ, worker_res = submit_docking_job(
            receptor_pdbqt=receptor_pdbqt,
            ligands=prepared_ligands,
            search_box=search_box,
            exhaustiveness=exhaustiveness,
            num_modes=num_modes,
            seed=seed,
            experiment_id=exp_id
        )

        worker_metrics = worker_res.get("metrics", {}) if isinstance(worker_res, dict) else {}
        worker_results = worker_res.get("results", []) if isinstance(worker_res, dict) else []
        strict_native_success = bool(
            succ
            and isinstance(worker_res, dict)
            and worker_res.get("status") == "COMPLETED"
            and worker_res.get("exit_code") == 0
            and worker_res.get("production_ready") is True
            and worker_res.get("execution_mode") == "NATIVE"
            and worker_res.get("tool") == "AutoDock Vina"
            and isinstance(worker_res.get("tool_version"), str)
            and worker_res.get("tool_version", "").lower().startswith("autodock vina")
            and worker_metrics.get("vina_identity_verified") is True
            and worker_metrics.get("vina_binary_sha256")
            and worker_metrics.get("stdout_sha256")
            and worker_metrics.get("output_pdbqt_hashes")
            and worker_res.get("worker_id")
            and worker_res.get("reproducibility_hash")
            and worker_results
            and not worker_res.get("failures")
            and all(
                r.get("result_origin") == "COMPUTED"
                and r.get("molecule_id")
                and r.get("docking_score") is not None
                and r.get("output_pdbqt_hash")
                and r.get("receptor_hash")
                and r.get("ligand_hash")
                and r.get("tool") == worker_res.get("tool")
                and r.get("tool_version") == worker_res.get("tool_version")
                and r.get("vina_binary_sha256") == worker_metrics.get("vina_binary_sha256")
                and r.get("output_pdbqt_hash") in worker_metrics.get("output_pdbqt_hashes", [])
                for r in worker_results
            )
        )

        if strict_native_success:
            worker_job_id = worker_res.get("job_id")
            worker_id = worker_res.get("worker_id")
            worker_env_hash = worker_res.get("environment_sha256")
            worker_is_native = True
            reproducibility_hash = worker_res.get("reproducibility_hash")
            exit_code = worker_res.get("exit_code")
            actual_tool = worker_res["tool"]
            actual_tool_version = worker_res["tool_version"]
            vina_binary_sha256 = worker_metrics.get("vina_binary_sha256")
            vina_version_output_sha256 = worker_metrics.get("vina_version_output_sha256")
            stdout_sha256 = worker_metrics.get("stdout_sha256")
            output_pdbqt_hashes = worker_metrics.get("output_pdbqt_hashes") or []

            for result in worker_results:
                m_id = result.get("molecule_id")
                score = result.get("docking_score")
                if m_id and score is not None:
                    docking_data[m_id] = {
                        "score": float(score),
                        "best_affinity_kcal_mol": result.get("best_affinity_kcal_mol"),
                        "poses_count": result.get("poses_count"),
                        "receptor_hash": result.get("receptor_hash"),
                        "ligand_hash": result.get("ligand_hash"),
                        "output_pdbqt_hash": result.get("output_pdbqt_hash"),
                        "stdout_sha256": result.get("stdout_sha256"),
                        "config_sha256": result.get("config_sha256"),
                    }
        else:
            exit_code = worker_res.get("exit_code") if isinstance(worker_res, dict) else None
            failures = worker_res.get("failures") if isinstance(worker_res, dict) else None
            worker_error = failures or (
                f"Worker response failed strict native attestation: status={worker_res.get('status')}, "
                f"exit_code={worker_res.get('exit_code')}, tool={worker_res.get('tool')}, "
                f"version={worker_res.get('tool_version')}"
                if isinstance(worker_res, dict)
                else str(worker_res)
            )

    elif result_origin == "IMPORTED":
        reader = csv.DictReader(io.StringIO(custom_scores_csv.strip()))
        for row in reader:
            m_id = row.get("molecule_id") or row.get("id")
            score_str = row.get("docking_score") or row.get("score") or row.get("affinity")
            if not m_id or score_str in (None, ""):
                raise ValueError("Each imported docking row requires molecule_id and docking_score")
            try:
                docking_data[m_id] = {"score": float(score_str)}
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid imported docking score for {m_id}: {score_str}") from exc

        dataset_ids = {m["id"] for m in in_ds["molecules"]}
        unknown_ids = sorted(set(docking_data) - dataset_ids)
        missing_ids = sorted(dataset_ids - set(docking_data))
        if unknown_ids:
            raise ValueError(f"Imported docking data contains molecule IDs outside the input dataset: {', '.join(unknown_ids)}")
        if missing_ids:
            raise ValueError(f"Imported docking data is incomplete; missing scores for: {', '.join(missing_ids)}")

    else:
        for m in in_ds["molecules"]:
            m_id = m["id"]
            n_rings = m.get("num_rings", 3)
            hba = m.get("hba", 5)
            hbd = m.get("hbd", 1)
            base_score = -5.0 - (n_rings * 0.8) - ((hba + hbd) * 0.2)
            score_bucket = int(hashlib.sha256(m_id.encode("utf-8")).hexdigest()[:8], 16) % 20
            noise = (score_bucket / 10.0) - 1.0
            docking_data[m_id] = {"score": round(max(-14.0, min(-4.0, base_score + noise)), 1)}

    if reproducibility_hash is None and docking_data:
        reproducibility_hash = compute_sha256(json.dumps({
            "origin": result_origin,
            "tool": actual_tool,
            "tool_version": actual_tool_version,
            "receptor_hash": receptor_hash,
            "parameters": {
                "center_x": center_x, "center_y": center_y, "center_z": center_z,
                "size_x": size_x, "size_y": size_y, "size_z": size_z,
                "exhaustiveness": exhaustiveness, "num_modes": num_modes, "seed": seed,
            },
            "scores": {key: value["score"] for key, value in sorted(docking_data.items())},
        }, sort_keys=True))

    # Process molecules
    conn = get_db_connection()
    c = conn.cursor()
    best_score = 999.0

    duration = round(time.time() - start_time, 2)
    final_status = 'completed' if worker_error is None and docking_data else 'failed'

    metrics = {
        "molecules_docked": len(docking_data),
        "grid_center": grid_center,
        "grid_size": grid_size,
        "exhaustiveness": exhaustiveness,
        "result_origin": result_origin,
        "duration_seconds": duration,
        "worker_job_id": worker_job_id,
        "worker_id": worker_id,
        "environment_sha256": worker_env_hash,
        "is_native_vina_executed": worker_is_native,
        "tool": actual_tool,
        "tool_version": actual_tool_version,
        "vina_binary_sha256": vina_binary_sha256,
        "vina_version_output_sha256": vina_version_output_sha256,
        "stdout_sha256": stdout_sha256,
        "output_pdbqt_hashes": output_pdbqt_hashes,
        "reproducibility_hash": reproducibility_hash,
        "error": str(worker_error) if worker_error else None
    }

    out_ds_id = None
    out_ds_label = None

    if final_status == "completed" and len(docking_data) > 0:
        v_row = conn.execute("SELECT MAX(version) as max_v FROM datasets WHERE project_id = ?", (project_id,)).fetchone()
        next_v = (v_row['max_v'] or 0) + 1
        out_ds_id = gen_id("ds")
        out_ds_label = f"{project['name'].replace(' ', '_')}_dataset_v{next_v}"

        passed_mols = [m for m in in_ds["molecules"] if m["id"] in docking_data]
        dataset_content_hash = compute_sha256("".join([m['id'] for m in passed_mols]))

        c.execute('''INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'Docking', ?, ?, ?)''',
                  (out_ds_id, project_id, f"Docked Dataset v{next_v}", next_v, out_ds_label, input_dataset_id,
                   f"Docking results for {receptor} using {actual_tool} ({result_origin}).", len(passed_mols), dataset_content_hash, now_iso()))

        for m in passed_mols:
            c.execute("INSERT OR IGNORE INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)",
                      (out_ds_id, m["id"], now_iso()))

    mols_in_count = len(in_ds["molecules"])
    mols_out_count = len(docking_data) if final_status == "completed" else 0
    mols_failed_count = mols_in_count - mols_out_count

    c.execute('''INSERT INTO experiments
                 (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (exp_id, project_id, experiment_name, 'docking', final_status, 'Docking', input_dataset_id, out_ds_id, actual_tool, actual_tool_version,
               start_ts, now_iso(), duration, mols_in_count, mols_out_count, mols_failed_count, 1, None, None,
               json.dumps(get_system_environment_info()),
               json.dumps({
                   "docking_tool": actual_tool, "tool_version": actual_tool_version,
                   "receptor": receptor, "grid_center": grid_center, "grid_size": grid_size, "exhaustiveness": exhaustiveness,
                   "seed": seed, "receptor_hash": receptor_hash, "result_origin": result_origin,
                   "center_x": center_x, "center_y": center_y, "center_z": center_z,
                   "size_x": size_x, "size_y": size_y, "size_z": size_z,
                   "num_modes": num_modes,
                   "receptor_pdbqt": receptor_pdbqt if result_origin == "COMPUTED" else None,
                   "prepared_ligands": prepared_ligands if result_origin == "COMPUTED" else None,
                   "source_file_sha256": compute_sha256(custom_scores_csv) if result_origin == "IMPORTED" else None,
                   "custom_scores_csv": custom_scores_csv if result_origin == "IMPORTED" else None
               }),
               json.dumps(metrics), "", "", notes, json.dumps([]), "", start_ts))

    if out_ds_id:
        c.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp_id, out_ds_id))
        c.execute('''INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
                     VALUES (?, ?, ?, 'experiment', ?, 'dataset', 'generated', ?, ?)''',
                  (gen_id("prov"), project_id, exp_id, out_ds_id, json.dumps({"role": "ligand_library", "sha256": dataset_content_hash}), now_iso()))

    if final_status == "completed":
        for m in in_ds["molecules"]:
            m_id = m["id"]

            if m_id not in docking_data:
                continue

            data = docking_data[m_id]
            score = data["score"]
            actual_rec_hash = data.get("receptor_hash") or receptor_hash
            actual_lig_hash = data.get("ligand_hash") or compute_sha256(m.get("smiles", ""))
            actual_poses_count = data.get("poses_count")

            best_score = min(best_score, score)

            c.execute('''INSERT INTO docking_results
                         (id, project_id, molecule_id, experiment_id, docking_score, result_origin, receptor, docking_tool, pose_identifier, binding_site_coords, center_x, center_y, center_z, size_x, size_y, size_z, exhaustiveness, seed, vina_version, receptor_file_hash, ligand_file_hash, rmsd_lower_bound, rmsd_upper_bound, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (gen_id("res"), project_id, m_id, exp_id, score, result_origin, receptor, actual_tool,
                       f"pose_best_of_{actual_poses_count}" if actual_poses_count else None, None, center_x, center_y, center_z, size_x, size_y, size_z, exhaustiveness, seed, actual_tool_version, actual_rec_hash, actual_lig_hash, None, None, now_iso()))

    if best_score == 999.0:
         best_score = None

    metrics["best_docking_score"] = best_score
    metrics["exit_code"] = exit_code

    # Update experiments again with best_score
    c.execute("UPDATE experiments SET metrics = ? WHERE id = ?", (json.dumps(metrics), exp_id))

    c.execute('''INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
                 VALUES (?, ?, ?, 'dataset', ?, 'experiment', 'wasUsedBy', ?, ?)''',
              (gen_id("prov"), project_id, input_dataset_id, exp_id, json.dumps({"role": "ligand_library"}), now_iso()))

    conn.commit()
    conn.close()

    if worker_error:
        # We optionally insert into experiment_failures here as well
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO experiment_failures
                     (id, experiment_id, molecule_id, molecule_name, smiles, pipeline_stage, error_type, error_message, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (gen_id("fail"), exp_id, "SYSTEM", "SYSTEM", "SYSTEM", "execution", "WorkerDockingError", str(worker_error), now_iso()))
        conn.commit()
        conn.close()

    return {
        "experiment_id": exp_id,
        "output_dataset_id": out_ds_id,
        "output_dataset_label": out_ds_label,
        "status": final_status,
        "exit_code": exit_code,
        "best_docking_score": best_score,
        "molecules_docked": len(docking_data),
        "metrics": metrics
    }

def import_or_run_admet(project_id: str,
                        input_dataset_id: str,
                        experiment_name: str = "In Silico ADMET Profiling",
                        tool_name: str = "SwissADME & pkCSM Engine",
                        result_origin: str = "IMPORTED",
                        custom_admet_csv: Optional[str] = None,
                        notes: str = "") -> dict:
    project = get_project(project_id)
    in_ds = get_dataset_detail(input_dataset_id)
    if not project or not in_ds:
        raise ValueError("Project or input dataset not found")

    result_origin = (result_origin or "").upper()
    if result_origin not in {"COMPUTED", "IMPORTED", "SIMULATED", "DEMO"}:
        raise ValueError("result_origin must be one of COMPUTED, IMPORTED, SIMULATED, or DEMO")
    if result_origin == "COMPUTED":
        raise ValueError("No native ADMET engine is configured; heuristic ADMET results cannot be labeled COMPUTED")
    if result_origin == "IMPORTED" and not custom_admet_csv:
        raise ValueError("IMPORTED ADMET requires custom_admet_csv; endpoint values are never synthesized")
    if result_origin in {"SIMULATED", "DEMO"} and custom_admet_csv:
        raise ValueError(f"{result_origin} ADMET cannot accept imported endpoint data")

    if result_origin == "IMPORTED":
        actual_tool_name = tool_name or "Imported ADMET data"
        actual_tool_version = "imported-unspecified"
    elif result_origin == "SIMULATED":
        actual_tool_name = "AIDD ADMET descriptor heuristic"
        actual_tool_version = "simulation-v1"
    else:
        actual_tool_name = "AIDD ADMET demo fixture"
        actual_tool_version = "demo-fixture-v1"

    exp_id = gen_id("exp")
    start_ts = now_iso()
    start_time = time.time()

    admet_map = {}
    source_hash = ""

    if custom_admet_csv:
        source_hash = compute_sha256(custom_admet_csv)
        reader = csv.DictReader(io.StringIO(custom_admet_csv.strip()))
        for row in reader:
            mid = row.get("molecule_id") or row.get("id")
            if mid:
                admet_map[mid] = row

    if result_origin == "IMPORTED":
        required_fields = {
            "gi_absorption", "bbb_permeant", "cyp3a4_inhibitor", "cyp2d6_inhibitor",
            "hepatotoxicity", "mutagenicity_ames", "herg_inhibition", "clearance_rate",
            "bioavailability_score", "admet_risk_level", "confidence",
        }
        dataset_ids = {m["id"] for m in in_ds["molecules"]}
        unknown_ids = sorted(set(admet_map) - dataset_ids)
        missing_ids = sorted(dataset_ids - set(admet_map))
        if unknown_ids:
            raise ValueError(f"Imported ADMET data contains molecule IDs outside the input dataset: {', '.join(unknown_ids)}")
        if missing_ids:
            raise ValueError(f"Imported ADMET data is incomplete; missing rows for: {', '.join(missing_ids)}")
        for mid, row in admet_map.items():
            missing_fields = sorted(field for field in required_fields if row.get(field) in (None, ""))
            if missing_fields:
                raise ValueError(f"Imported ADMET row {mid} is missing fields: {', '.join(missing_fields)}")

    end_time = time.time()
    duration = round(end_time - start_time, 3)
    end_ts = now_iso()

    with get_db() as conn:
        v_row = conn.execute("SELECT MAX(version) as max_v FROM datasets WHERE project_id = ?", (project_id,)).fetchone()
        next_v = (v_row['max_v'] or 0) + 1
        out_ds_id = gen_id("ds")
        out_ds_label = f"{project['name'].replace(' ', '_')}_dataset_v{next_v}"
        dataset_content_hash = compute_sha256(f"admet_{out_ds_label}_{len(in_ds['molecules'])}")

        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'ADMET', ?, ?, ?)
            """,
            (
                out_ds_id, project_id, f"ADMET Dataset v{next_v}", next_v, out_ds_label,
                input_dataset_id,
                f"ADMET records produced via {actual_tool_name} [{result_origin}]. Total {len(in_ds['molecules'])} molecules.",
                len(in_ds["molecules"]), dataset_content_hash, end_ts
            )
        )

        for m in in_ds["molecules"]:
            conn.execute(
                "INSERT OR IGNORE INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)",
                (out_ds_id, m["id"], end_ts)
            )

        parameters = {
            "admet_tool": actual_tool_name,
            "tool_version": actual_tool_version,
            "result_origin": result_origin,
            "models_included": ["Gastrointestinal Absorption (BOILED-Egg)", "BBB Permeability", "CYP450 3A4/2D6 Inhibition", "Ames Mutagenicity", "hERG Cardiotoxicity"],
            "source_file_sha256": source_hash or None,
            "custom_admet_csv": custom_admet_csv if result_origin == "IMPORTED" else None,
            "input_dataset": in_ds["version_label"],
            "notes": notes
        }
        metrics = {
            "total_evaluated": len(in_ds["molecules"]),
            "result_origin": result_origin,
            "high_gi_absorption_rate": None,
            "low_admet_risk_count": None,
        }
        log_lines = [
            f"[{start_ts}] [INFO] Processing ADMET records using {actual_tool_name} [Origin: {result_origin}]",
            f"[{start_ts}] [INFO] Input dataset: {in_ds['version_label']} ({len(in_ds['molecules'])} compounds)",
            f"[{end_ts}] [INFO] Attached pharmacokinetic and toxicity endpoints with explicit origin tags",
            f"[{end_ts}] [INFO] Output dataset created: {out_ds_label}"
        ]

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'admet', 'completed', 'ADMET', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', ?, '[]', '', ?)
            """,
            (
                exp_id, project_id, experiment_name, input_dataset_id, out_ds_id,
                actual_tool_name, actual_tool_version, start_ts, end_ts, duration, len(in_ds["molecules"]), len(in_ds["molecules"]),
                json.dumps(get_system_environment_info()), json.dumps(parameters), json.dumps(metrics),
                "\n".join(log_lines), notes, start_ts
            )
        )

        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp_id, out_ds_id))

        high_gi_count = 0
        low_risk_count = 0
        for m in in_ds["molecules"]:
            mid = m["id"]
            if mid in admet_map:
                r = admet_map[mid]
                gi = r.get("gi_absorption", "High")
                bbb = r.get("bbb_permeant", "No")
                cyp3a4 = r.get("cyp3a4_inhibitor", "Yes")
                cyp2d6 = r.get("cyp2d6_inhibitor", "No")
                hep = r.get("hepatotoxicity", "Negative")
                ames = r.get("mutagenicity_ames", "Negative")
                herg = r.get("herg_inhibition", "Low Risk")
                clr = float(r.get("clearance_rate", 5.2))
                bio = float(r.get("bioavailability_score", 0.55))
                risk = r.get("admet_risk_level", "Low Risk")
                conf = float(r.get("confidence", 0.90))
            else:
                mw = m.get("molecular_weight", 400.0)
                logp = m.get("logp", 3.0)
                tpsa = m.get("tpsa", 70.0)

                gi = "High" if (tpsa <= 130.0 and mw <= 500.0) else "Low"
                bbb = "Yes" if (tpsa < 90.0 and 1.5 < logp < 4.5 and mw < 420.0) else "No"
                cyp3a4 = "Yes" if (logp > 2.8 or mw > 400.0) else "No"
                cyp2d6 = "Yes" if (any(a in m["smiles"] for a in ['N', 'n']) and 2.0 < logp < 4.0) else "No"
                hep = "High Risk" if (logp > 4.5 or mw > 500.0) else "Low Risk"
                ames = "Positive" if any(x in m["smiles"] for x in ['[N+](=O)[O-]', 'N=N', 'N-N']) else "Negative"
                herg = "High Risk" if (logp > 3.8 and any(x in m["smiles"] for x in ['CCN', 'CCN(C)C', 'CCN1'])) else "Low Risk"
                clr = round(max(0.5, 8.5 - 0.8 * logp + 0.005 * mw), 2)
                bio = 0.55 if m.get("lipinski_pass") else 0.17
                conf = 0.85

                risk_points = 0
                if gi == "Low": risk_points += 1
                if hep == "High Risk": risk_points += 2
                if ames == "Positive": risk_points += 2
                if herg == "High Risk": risk_points += 2

                if risk_points <= 1: risk = "Low Risk"
                elif risk_points <= 3: risk = "Moderate Risk"
                else: risk = "High Risk"

            if gi == "High":
                high_gi_count += 1
            if risk == "Low Risk":
                low_risk_count += 1

            conn.execute(
                """
                INSERT OR REPLACE INTO admet_results
                (id, project_id, molecule_id, experiment_id, result_origin, provider_tool, model_version, endpoint_name, confidence_score, units, source_file_hash, gi_absorption, bbb_permeant, cyp3a4_inhibitor, cyp2d6_inhibitor, hepatotoxicity, mutagenicity_ames, herg_inhibition, clearance_rate, bioavailability_score, admet_risk_level, risk_details, disclaimer, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ConsensusADMET', ?, 'categorical/mL/min/kg', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Computational prediction. In vitro validation required.', ?)
                """,
                (
                    gen_id("admet"), project_id, mid, exp_id, result_origin,
                    actual_tool_name, actual_tool_version, conf, source_hash or None,
                    gi, bbb, cyp3a4, cyp2d6, hep, ames, herg, clr, bio, risk,
                    json.dumps({"gi": gi, "bbb": bbb, "cyp3a4": cyp3a4, "cyp2d6": cyp2d6, "hep": hep, "ames": ames, "herg": herg}),
                    end_ts
                )
            )

        metrics["high_gi_absorption_rate"] = round((high_gi_count / len(in_ds["molecules"])) * 100.0, 1) if in_ds["molecules"] else 0.0
        metrics["low_admet_risk_count"] = low_risk_count
        conn.execute("UPDATE experiments SET metrics = ? WHERE id = ?", (json.dumps(metrics), exp_id))

        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'dataset', ?, 'experiment', 'processed_by', ?, ?)
            """,
            (gen_id("edge"), project_id, input_dataset_id, exp_id, json.dumps({"stage": "admet", "origin": result_origin}), end_ts)
        )
        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'experiment', ?, 'dataset', 'generated_from', ?, ?)
            """,
            (gen_id("edge"), project_id, exp_id, out_ds_id, json.dumps({"action": "admet_dataset", "sha256": dataset_content_hash}), end_ts)
        )

        conn.execute("UPDATE projects SET current_stage = 'ADMET', updated_at = ? WHERE id = ?", (end_ts, project_id))

    return {
        "experiment_id": exp_id,
        "output_dataset_id": out_ds_id,
        "output_dataset_label": out_ds_label,
        "result_origin": result_origin,
        "molecules_evaluated": len(in_ds["molecules"])
    }

# -------------------------------------------------------------------
# CANDIDATE SELECTION & WEIGHTED RANKING
# -------------------------------------------------------------------

def calculate_candidate_rankings(project_id: str,
                                 input_dataset_id: Optional[str] = None,
                                 weights: Optional[Dict[str, float]] = None,
                                 missing_data_policy: str = "RENORMALIZE",
                                 experiment_name: str = "Candidate Multi-Parameter Ranking",
                                 notes: str = "") -> dict:
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found")

    w = weights or {
        "docking": 0.35,
        "qsar": 0.25,
        "admet": 0.25,
        "druglikeness": 0.15
    }
    w_sum = max(0.001, sum(w.values()))
    w_dock = w.get("docking", 0.35) / w_sum
    w_qsar = w.get("qsar", 0.25) / w_sum
    w_admet = w.get("admet", 0.25) / w_sum
    w_qed = w.get("druglikeness", 0.15) / w_sum

    normalization_doc = (
        "Docking: Inverted Min-Max [-12.0 to -5.0 kcal/mol -> 1.0 to 0.0] (MINIMIZE); "
        "QSAR: Linear pIC50 [5.0 to 10.0 -> 0.0 to 1.0] (MAXIMIZE); "
        "ADMET: Safety scale [Low=1.0, Mod=0.6, High=0.2]; "
        "Drug-likeness: QED [0.0 to 1.0] (MAXIMIZE)"
    )
    formula_str = f"Composite Score = ({w_dock*100:.1f}% * Dock_Norm) + ({w_qsar*100:.1f}% * QSAR_Norm) + ({w_admet*100:.1f}% * ADMET_Norm) + ({w_qed*100:.1f}% * QED_Norm)"

    start_ts = now_iso()
    start_time = time.time()
    exp_id = gen_id("exp")

    with get_db() as conn:
        if input_dataset_id:
            molecules = conn.execute(
                """
                SELECT m.*,
                       (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_score,
                       (SELECT dr.result_origin FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_origin,
                       (SELECT ar.admet_risk_level FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_risk_level,
                       (SELECT ar.result_origin FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_origin
                FROM molecules m
                JOIN dataset_molecules dm ON m.id = dm.molecule_id
                WHERE dm.dataset_id = ?
                """,
                (input_dataset_id,)
            ).fetchall()
        else:
            molecules = conn.execute(
                """
                SELECT m.*,
                       (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_score,
                       (SELECT dr.result_origin FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_origin,
                       (SELECT ar.admet_risk_level FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_risk_level,
                       (SELECT ar.result_origin FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_origin
                FROM molecules m
                WHERE m.project_id = ?
                """,
                (project_id,)
            ).fetchall()

        if not molecules:
            return {"total_ranked": 0, "rankings": []}

        scores_list = []
        for m in molecules:
            dock_score = m["docking_score"]
            risk = m["admet_risk_level"]
            qed_val = m["qed"] if m["qed"] is not None else 0.5
            input_origins = {m["docking_origin"], m["admet_origin"], m["descriptor_origin"]}
            ranking_origin = "DEMO" if "DEMO" in input_origins else "SIMULATED"

            is_complete = 1
            missing_fields = []
            if dock_score is None:
                is_complete = 0
                missing_fields.append("docking_score")
            if risk is None:
                is_complete = 0
                missing_fields.append("admet_risk_level")

            if missing_data_policy == "EXCLUDE" and not is_complete:
                continue

            if dock_score is not None:
                s_dock = max(0.0, min(1.0, (-dock_score - 5.0) / 7.0))
            else:
                s_dock = 0.30 if missing_data_policy == "PENALIZE_DEFAULT" else 0.0

            s_qsar = max(0.0, min(1.0, (s_dock * 0.85 + qed_val * 0.15)))

            if risk == "Low Risk": s_admet = 1.0
            elif risk == "Moderate Risk": s_admet = 0.60
            elif risk == "High Risk": s_admet = 0.20
            else: s_admet = 0.30 if missing_data_policy == "PENALIZE_DEFAULT" else 0.0

            s_qed = qed_val

            if missing_data_policy == "RENORMALIZE" and not is_complete:
                active_weights = {"druglikeness": w_qed, "qsar": w_qsar}
                if dock_score is not None: active_weights["docking"] = w_dock
                if risk is not None: active_weights["admet"] = w_admet
                sum_act = sum(active_weights.values()) or 1.0
                cur_wd = active_weights.get("docking", 0.0) / sum_act
                cur_wq = active_weights.get("qsar", 0.0) / sum_act
                cur_wa = active_weights.get("admet", 0.0) / sum_act
                cur_wqed = active_weights.get("druglikeness", 0.0) / sum_act
            else:
                cur_wd, cur_wq, cur_wa, cur_wqed = w_dock, w_qsar, w_admet, w_qed

            contrib_dock = cur_wd * s_dock * 100.0
            contrib_qsar = cur_wq * s_qsar * 100.0
            contrib_admet = cur_wa * s_admet * 100.0
            contrib_qed = cur_wqed * s_qed * 100.0
            composite = contrib_dock + contrib_qsar + contrib_admet + contrib_qed

            raw_components = {
                "docking_raw_kcal_mol": dock_score,
                "qsar_raw_pIC50_est": round(5.0 + s_qsar * 4.5, 2),
                "admet_risk_raw": risk or "Missing",
                "qed_raw": round(qed_val, 3)
            }
            weighted_components = {
                "docking_norm": round(s_dock, 4),
                "docking_weight_pct": round(cur_wd * 100, 1),
                "docking_contrib": round(contrib_dock, 2),
                "qsar_norm": round(s_qsar, 4),
                "qsar_weight_pct": round(cur_wq * 100, 1),
                "qsar_contrib": round(contrib_qsar, 2),
                "admet_norm": round(s_admet, 4),
                "admet_weight_pct": round(cur_wa * 100, 1),
                "admet_contrib": round(contrib_admet, 2),
                "qed_norm": round(s_qed, 4),
                "qed_weight_pct": round(cur_wqed * 100, 1),
                "qed_contrib": round(contrib_qed, 2)
            }

            scores_list.append({
                "molecule_id": m["id"],
                "molecule_name": m["name"],
                "smiles": m["smiles"],
                "composite_score": round(composite, 2),
                "raw_components": raw_components,
                "weighted_components": weighted_components,
                "is_data_complete": is_complete,
                "docking_score": dock_score,
                "admet_risk_level": risk,
                "result_origin": ranking_origin,
            })

        scores_list.sort(key=lambda x: x["composite_score"], reverse=True)

        for rank, s in enumerate(scores_list, start=1):
            s["rank_position"] = rank
            if s["composite_score"] >= 78.0: tier = "Lead Candidate"
            elif s["composite_score"] >= 65.0: tier = "Backup Lead"
            elif s["composite_score"] >= 50.0: tier = "Follow-up"
            else: tier = "Deprioritized"
            s["tier"] = tier

        end_time = time.time()
        duration = round(end_time - start_time, 3)
        end_ts = now_iso()
        experiment_origin = "DEMO" if any(s["result_origin"] == "DEMO" for s in scores_list) else "SIMULATED"

        parameters = {
            "weights": {"docking": w_dock, "qsar": w_qsar, "admet": w_admet, "druglikeness": w_qed},
            "missing_data_policy": missing_data_policy,
            "normalization_method": normalization_doc,
            "scoring_formula": formula_str,
            "tier_thresholds": "Lead >= 78, Backup >= 65, Follow-up >= 50",
            "notes": notes,
            "result_origin": experiment_origin,
        }
        leads_count = sum(1 for s in scores_list if s["tier"] == "Lead Candidate")
        backups_count = sum(1 for s in scores_list if s["tier"] == "Backup Lead")
        metrics = {
            "total_molecules_ranked": len(scores_list),
            "lead_candidates_identified": leads_count,
            "backup_leads_identified": backups_count,
            "top_candidate_id": scores_list[0]["molecule_id"] if scores_list else None,
            "top_composite_score": scores_list[0]["composite_score"] if scores_list else 0.0
        }
        log_lines = [
            f"[{start_ts}] [INFO] Starting Candidate Ranking Optimization for '{project['name']}'",
            f"[{start_ts}] [INFO] Formula: {formula_str}",
            f"[{start_ts}] [INFO] Missing Data Policy: {missing_data_policy}",
            f"[{end_ts}] [INFO] Identified {leads_count} Leads, {backups_count} Backups",
            f"[{end_ts}] [INFO] Top Rank: #{1} {scores_list[0]['molecule_name']} ({scores_list[0]['composite_score']}/100)"
        ]

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, ?, 'candidate_ranking', 'completed', 'Candidate Selection', ?, NULL, 'AIDD Heuristic Multi-Objective Optimizer', ?, ?, ?, ?, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', ?, '[]', '', ?)
            """,
            (
                exp_id, project_id, experiment_name, input_dataset_id, "demo-fixture-v1" if experiment_origin == "DEMO" else "simulation-v1",
                start_ts, end_ts, duration, len(scores_list), len(scores_list),
                json.dumps(get_system_environment_info()), json.dumps(parameters), json.dumps(metrics),
                "\n".join(log_lines), notes, start_ts
            )
        )

        for s in scores_list:
            wc = s["weighted_components"]
            conn.execute(
                """
                INSERT OR REPLACE INTO candidate_scores
                (id, project_id, molecule_id, experiment_id, composite_score, result_origin, docking_component, qsar_component, admet_component, druglikeness_component, weights_applied, formula_expression, normalization_method, raw_components_json, weighted_components_json, missing_data_policy, is_data_complete, rank_position, tier, selection_notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gen_id("cand"), project_id, s["molecule_id"], exp_id,
                    s["composite_score"], s["result_origin"],
                    wc["docking_contrib"], wc["qsar_contrib"], wc["admet_contrib"], wc["qed_contrib"],
                    json.dumps({"docking": w_dock, "qsar": w_qsar, "admet": w_admet, "druglikeness": w_qed}),
                    formula_str, normalization_doc,
                    json.dumps(s["raw_components"]), json.dumps(s["weighted_components"]),
                    missing_data_policy, s["is_data_complete"], s["rank_position"], s["tier"],
                    f"Rank #{s['rank_position']} via multi-parameter composite scoring.",
                    start_ts
                )
            )
            conn.execute("UPDATE molecules SET tier = ? WHERE id = ?", (s["tier"], s["molecule_id"]))

        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'experiment', ?, 'candidate_set', 'selected_from', ?, ?)
            """,
            (gen_id("edge"), project_id, exp_id, f"candidates_{project_id}", json.dumps({"leads_count": leads_count}), end_ts)
        )

        conn.execute("UPDATE projects SET current_stage = 'Candidate Selection', updated_at = ? WHERE id = ?", (end_ts, project_id))

    return {
        "experiment_id": exp_id,
        "formula": formula_str,
        "normalization_method": normalization_doc,
        "missing_data_policy": missing_data_policy,
        "weights": {"docking": w_dock, "qsar": w_qsar, "admet": w_admet, "druglikeness": w_qed},
        "total_ranked": len(scores_list),
        "lead_count": leads_count,
        "backup_count": backups_count,
        "top_candidates": scores_list[:10]
    }

def get_candidate_rankings(project_id: str) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT cs.*,
                   m.name as molecule_name,
                   m.smiles,
                   m.formula,
                   m.molecular_weight,
                   m.logp,
                   m.tpsa,
                   m.qed,
                   m.lipinski_violations,
                   m.svg_structure,
                   dr.docking_score,
                   dr.result_origin as docking_origin,
                   dr.receptor as docking_receptor,
                   ar.admet_risk_level,
                   ar.result_origin as admet_origin,
                   ar.gi_absorption,
                   ar.bbb_permeant,
                   ar.hepatotoxicity
            FROM candidate_scores cs
            JOIN molecules m ON cs.molecule_id = m.id
            LEFT JOIN docking_results dr ON cs.molecule_id = dr.molecule_id AND cs.project_id = dr.project_id
            LEFT JOIN admet_results ar ON cs.molecule_id = ar.molecule_id AND cs.project_id = ar.project_id
            WHERE cs.project_id = ?
            ORDER BY cs.composite_score DESC
            """,
            (project_id,)
        ).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            try: d["raw_components_json"] = json.loads(d["raw_components_json"]) if d["raw_components_json"] else {}
            except: pass
            try: d["weighted_components_json"] = json.loads(d["weighted_components_json"]) if d["weighted_components_json"] else {}
            except: pass
            result.append(d)
        return result

# -------------------------------------------------------------------
# EXPERIMENT REPRODUCTION & MANIFESTS
# -------------------------------------------------------------------

def reproduce_experiment(experiment_id: str) -> dict:
    orig_exp = get_experiment_detail(experiment_id)
    if not orig_exp:
        raise ValueError("Original experiment not found")

    project_id = orig_exp["project_id"]
    exp_type = orig_exp["experiment_type"]
    in_ds_id = orig_exp["input_dataset_id"]
    params = orig_exp.get("parameters", {})

    new_name = f"Reproduction of '{orig_exp['name']}'"
    new_exp_res = None

    if exp_type == "preprocessing":
        new_exp_res = run_standardization_experiment(
            project_id=project_id,
            input_dataset_id=in_ds_id,
            experiment_name=new_name,
            remove_salts=params.get("remove_salts", True),
            neutralize_charges=params.get("neutralize_charges", True),
            filter_lipinski=params.get("filter_lipinski", False),
            max_mw=params.get("max_mw", 550.0),
            max_logp=params.get("max_logp", 5.5),
            notes=f"Reproduced from experiment {experiment_id}"
        )
    elif exp_type == "docking":
        new_exp_res = import_or_run_docking(
            project_id=project_id,
            input_dataset_id=in_ds_id,
            experiment_name=new_name,
            docking_tool=params.get("docking_tool", "AutoDock Vina"),
            receptor=params.get("receptor", "EGFR Kinase Domain"),
            grid_center=params.get("grid_center", "x=22.0, y=0.5, z=52.8"),
            grid_size=params.get("grid_size", "20 x 20 x 20 Å"),
            center_x=params.get("center_x", 22.0),
            center_y=params.get("center_y", 0.5),
            center_z=params.get("center_z", 52.8),
            size_x=params.get("size_x", 20.0),
            size_y=params.get("size_y", 20.0),
            size_z=params.get("size_z", 20.0),
            exhaustiveness=params.get("exhaustiveness", 16),
            seed=params.get("seed", 42),
            result_origin=params.get("result_origin", "IMPORTED"),
            custom_scores_csv=params.get("custom_scores_csv"),
            notes=f"Reproduced from experiment {experiment_id}",
            receptor_pdbqt=params.get("receptor_pdbqt"),
            prepared_ligands=params.get("prepared_ligands"),
            num_modes=params.get("num_modes", 9)
        )
    elif exp_type == "admet":
        new_exp_res = import_or_run_admet(
            project_id=project_id,
            input_dataset_id=in_ds_id,
            experiment_name=new_name,
            tool_name=orig_exp["tool"],
            result_origin=params.get("result_origin", "IMPORTED"),
            custom_admet_csv=params.get("custom_admet_csv"),
            notes=f"Reproduced from experiment {experiment_id}"
        )
    elif exp_type == "candidate_ranking":
        new_exp_res = calculate_candidate_rankings(
            project_id=project_id,
            input_dataset_id=in_ds_id,
            weights=params.get("weights"),
            missing_data_policy=params.get("missing_data_policy", "RENORMALIZE"),
            experiment_name=new_name,
            notes=f"Reproduced from experiment {experiment_id}"
        )
    else:
        raise ValueError(f"Reproduction not supported for experiment type '{exp_type}'")

    new_exp_id = new_exp_res["experiment_id"]
    new_exp = get_experiment_detail(new_exp_id)

    match = 1
    diff_reasons = []
    if orig_exp.get("molecules_out") != new_exp.get("molecules_out"):
        match = 0
        diff_reasons.append(f"Molecules out mismatch: {orig_exp.get('molecules_out')} vs {new_exp.get('molecules_out')}")
    if orig_exp.get("molecules_failed") != new_exp.get("molecules_failed"):
        match = 0
        diff_reasons.append(f"Failures count mismatch: {orig_exp.get('molecules_failed')} vs {new_exp.get('molecules_failed')}")

    if orig_exp.get("tool") != new_exp.get("tool"):
        match = 0
        diff_reasons.append(f"Tool mismatch: {orig_exp.get('tool')} vs {new_exp.get('tool')}")
    if orig_exp.get("tool_version") != new_exp.get("tool_version"):
        match = 0
        diff_reasons.append(f"Tool version mismatch: {orig_exp.get('tool_version')} vs {new_exp.get('tool_version')}")

    if exp_type == "docking":
        relevant_parameters = (
            "result_origin", "receptor_hash", "center_x", "center_y", "center_z",
            "size_x", "size_y", "size_z", "exhaustiveness", "num_modes", "seed",
        )
        new_params = new_exp.get("parameters", {})
        for key in relevant_parameters:
            if params.get(key) != new_params.get(key):
                match = 0
                diff_reasons.append(f"Docking parameter {key} mismatch: {params.get(key)!r} vs {new_params.get(key)!r}")

        original_rows = {row["molecule_id"]: row for row in orig_exp.get("docking_results", [])}
        reproduced_rows = {row["molecule_id"]: row for row in new_exp.get("docking_results", [])}
        for molecule_id in sorted(set(original_rows) | set(reproduced_rows)):
            original_row = original_rows.get(molecule_id)
            reproduced_row = reproduced_rows.get(molecule_id)
            if original_row is None or reproduced_row is None:
                match = 0
                diff_reasons.append(f"Docking result presence mismatch for {molecule_id}")
                continue
            original_score = float(original_row["docking_score"])
            reproduced_score = float(reproduced_row["docking_score"])
            if not math.isclose(original_score, reproduced_score, rel_tol=0.0, abs_tol=1e-6):
                match = 0
                diff_reasons.append(f"Docking score mismatch for {molecule_id}: {original_score} vs {reproduced_score}")
            for field in ("result_origin", "receptor_file_hash", "ligand_file_hash"):
                if original_row.get(field) != reproduced_row.get(field):
                    match = 0
                    diff_reasons.append(
                        f"Docking {field} mismatch for {molecule_id}: {original_row.get(field)!r} vs {reproduced_row.get(field)!r}"
                    )

        original_metrics = orig_exp.get("metrics", {})
        reproduced_metrics = new_exp.get("metrics", {})
        for field in ("reproducibility_hash", "result_origin"):
            if original_metrics.get(field) != reproduced_metrics.get(field):
                match = 0
                diff_reasons.append(
                    f"Docking {field} mismatch: {original_metrics.get(field)!r} vs {reproduced_metrics.get(field)!r}"
                )
        if params.get("result_origin") == "COMPUTED":
            for field in ("worker_id", "exit_code", "vina_binary_sha256"):
                if original_metrics.get(field) != reproduced_metrics.get(field):
                    match = 0
                    diff_reasons.append(
                        f"Native attestation {field} mismatch: {original_metrics.get(field)!r} vs {reproduced_metrics.get(field)!r}"
                    )

    with get_db() as conn:
        conn.execute(
            "UPDATE experiments SET reproduction_of_id = ?, reproduction_match = ? WHERE id = ?",
            (experiment_id, match, new_exp_id)
        )
        conn.execute(
            """
            INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
            VALUES (?, ?, ?, 'experiment', ?, 'experiment', 'reproduction_of', ?, ?)
            """,
            (gen_id("edge"), project_id, new_exp_id, experiment_id, json.dumps({"match": match, "diffs": diff_reasons}), now_iso())
        )

    return {
        "original_experiment_id": experiment_id,
        "reproduced_experiment_id": new_exp_id,
        "reproduction_match": bool(match),
        "diff_reasons": diff_reasons,
        "new_experiment": new_exp
    }

def generate_experiment_manifest(experiment_id: str) -> dict:
    exp = get_experiment_detail(experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    in_ds = get_dataset_detail(exp["input_dataset_id"]) if exp["input_dataset_id"] else None
    out_ds = get_dataset_detail(exp["output_dataset_id"]) if exp["output_dataset_id"] else None

    return {
        "$schema": "https://aidd-lab-os.org/schemas/reproducibility_manifest_v1.json",
        "manifest_version": "1.2.0",
        "generated_at": now_iso(),
        "experiment": {
            "id": exp["id"],
            "project_id": exp["project_id"],
            "name": exp["name"],
            "type": exp["experiment_type"],
            "stage": exp["stage"],
            "status": exp["status"],
            "is_immutable_locked": bool(exp["is_locked"]),
            "started_at": exp["started_at"],
            "completed_at": exp["completed_at"],
            "duration_seconds": exp["duration_seconds"],
            "reproduction_of": exp.get("reproduction_of_id"),
            "reproduction_match": exp.get("reproduction_match")
        },
        "computational_environment": exp.get("environment_info", {}),
        "tooling": {
            "tool": exp["tool"],
            "version": exp["tool_version"]
        },
        "input_dataset": {
            "id": in_ds["id"] if in_ds else None,
            "version_label": in_ds["version_label"] if in_ds else None,
            "molecule_count": in_ds["molecule_count"] if in_ds else None,
            "sha256_hash": in_ds.get("sha256_hash") if in_ds else None
        },
        "output_dataset": {
            "id": out_ds["id"] if out_ds else None,
            "version_label": out_ds["version_label"] if out_ds else None,
            "molecule_count": out_ds["molecule_count"] if out_ds else None,
            "sha256_hash": out_ds.get("sha256_hash") if out_ds else None
        },
        "parameters": exp.get("parameters", {}),
        "metrics": exp.get("metrics", {}),
        "failures_count": len(exp.get("failures", [])),
        "failures_sample": exp.get("failures", [])[:5],
        "artifacts": [
            {
                "id": a["id"],
                "name": a["name"],
                "file_type": a["file_type"],
                "size_bytes": a["file_size_bytes"],
                "sha256_hash": a["sha256_hash"]
            }
            for a in exp.get("artifacts", [])
        ],
        "provenance_upstream": exp.get("provenance_upstream", []),
        "provenance_downstream": exp.get("provenance_downstream", [])
    }

def append_experiment_note(experiment_id: str, note_text: str, author: str = "Researcher") -> dict:
    exp = get_experiment_detail(experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    with get_db() as conn:
        row = conn.execute("SELECT notes_log FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        cur_log = json.loads(row["notes_log"]) if row and row["notes_log"] else []
        new_entry = {
            "timestamp": now_iso(),
            "author": author,
            "text": note_text
        }
        cur_log.append(new_entry)
        conn.execute("UPDATE experiments SET notes_log = ? WHERE id = ?", (json.dumps(cur_log), experiment_id))

    return {"status": "appended", "notes_log": cur_log}

# -------------------------------------------------------------------
# PROJECT REPRODUCIBILITY BUNDLE (ZIP EXPORT)
# -------------------------------------------------------------------

def generate_project_reproducibility_bundle(project_id: str) -> bytes:
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found")

    datasets = get_project_datasets(project_id)
    experiments = list_experiments(project_id)
    candidates = get_candidate_rankings(project_id)
    decisions = list_decision_logs(project_id)
    provenance = get_provenance_graph(project_id)
    report_data = generate_reproducibility_report_data(project_id)

    zip_buffer = io.BytesIO()
    checksums = []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. Project Manifest
        proj_manifest = {
            "$schema": "https://aidd-lab-os.org/schemas/project_bundle_v1.json",
            "project": project,
            "environment": get_system_environment_info(),
            "dataset_count": len(datasets),
            "experiment_count": len(experiments),
            "candidate_count": len(candidates),
            "generated_at": now_iso()
        }
        manifest_bytes = json.dumps(proj_manifest, indent=2).encode('utf-8')
        zf.writestr("project_manifest.json", manifest_bytes)
        checksums.append(f"{compute_sha256(manifest_bytes)}  project_manifest.json")

        # 2. Provenance DAG
        prov_bytes = json.dumps(provenance, indent=2).encode('utf-8')
        zf.writestr("provenance.json", prov_bytes)
        checksums.append(f"{compute_sha256(prov_bytes)}  provenance.json")

        # 3. Decision Log
        dec_bytes = json.dumps(decisions, indent=2).encode('utf-8')
        zf.writestr("decisions/decision_logs.json", dec_bytes)
        checksums.append(f"{compute_sha256(dec_bytes)}  decisions/decision_logs.json")

        # 4. Datasets CSVs
        for d in datasets:
            csv_str = export_dataset_csv(d["id"])
            csv_bytes = csv_str.encode('utf-8')
            filename = f"datasets/{d['version_label']}.csv"
            zf.writestr(filename, csv_bytes)
            checksums.append(f"{compute_sha256(csv_bytes)}  {filename}")

        # 5. Experiment Manifests
        for e in experiments:
            exp_manifest = generate_experiment_manifest(e["id"])
            exp_bytes = json.dumps(exp_manifest, indent=2).encode('utf-8')
            filename = f"experiments/manifest_{e['id']}.json"
            zf.writestr(filename, exp_bytes)
            checksums.append(f"{compute_sha256(exp_bytes)}  {filename}")

        # 6. Candidates CSV
        cand_csv = io.StringIO()
        cand_writer = csv.writer(cand_csv)
        cand_writer.writerow(["rank", "molecule_id", "name", "composite_score", "docking_score", "admet_risk", "mw", "logp", "tpsa", "tier", "origin"])
        for c in candidates:
            cand_writer.writerow([
                c["rank_position"], c["molecule_id"], c["molecule_name"],
                c["composite_score"], c.get("docking_score", ""), c.get("admet_risk_level", ""),
                c["molecular_weight"], c["logp"], c["tpsa"], c["tier"], c.get("result_origin") or "UNKNOWN"
            ])
        cand_bytes = cand_csv.getvalue().encode('utf-8')
        zf.writestr("candidates/ranked_candidates.csv", cand_bytes)
        checksums.append(f"{compute_sha256(cand_bytes)}  candidates/ranked_candidates.csv")

        # 7. Failures CSV
        failures = report_data.get("all_failures", [])
        fail_csv = io.StringIO()
        fail_writer = csv.writer(fail_csv)
        fail_writer.writerow(["failure_id", "experiment_id", "molecule_id", "name", "error_type", "error_message", "pipeline_stage", "timestamp"])
        for f in failures:
            fail_writer.writerow([f["id"], f["experiment_id"], f.get("molecule_id", ""), f.get("molecule_name", ""), f["error_type"], f["error_message"], f["pipeline_stage"], f["created_at"]])
        fail_bytes = fail_csv.getvalue().encode('utf-8')
        zf.writestr("failures/failure_audit.csv", fail_bytes)
        checksums.append(f"{compute_sha256(fail_bytes)}  failures/failure_audit.csv")

        # 8. Checksums file
        zf.writestr("checksums.sha256", "\n".join(checksums) + "\n")

        # 9. README.md
        readme = f"""# AIDD Lab OS Reproducibility Bundle
Project: {project['name']}
Target: {project['target_protein']}
Indication: {project['disease_indication']}
Generated: {now_iso()}

This package contains complete cryptographic and relational scientific records for all datasets,
experiments, parameters, docking scores, ADMET evaluations, and candidate rankings.
To verify integrity:
  sha256sum -c checksums.sha256
"""
        zf.writestr("README.md", readme.encode('utf-8'))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# -------------------------------------------------------------------
# MOLECULES RETRIEVAL & DETAIL
# -------------------------------------------------------------------


def list_molecules(project_id: str,
                   search: Optional[str] = None,
                   stage: Optional[str] = None,
                   lipinski_only: bool = False,
                   min_mw: Optional[float] = None,
                   max_mw: Optional[float] = None,
                   min_logp: Optional[float] = None,
                   max_logp: Optional[float] = None,
                   max_docking: Optional[float] = None,
                   tier: Optional[str] = None,
                   sort_by: str = "created_at",
                   sort_order: str = "desc",
                   limit: int = 100,
                   offset: int = 0) -> dict:
    with get_db() as conn:
        query = """
            SELECT m.*,
                   (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_score,
                   (SELECT dr.result_origin FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_origin,
                   (SELECT dr.receptor FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_receptor,
                   (SELECT ar.admet_risk_level FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_risk_level,
                   (SELECT ar.result_origin FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_origin,
                   (SELECT ar.gi_absorption FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as gi_absorption,
                   (SELECT ar.bbb_permeant FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as bbb_permeant,
                   (SELECT ar.hepatotoxicity FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as hepatotoxicity,
                   (SELECT cs.composite_score FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as candidate_score,
                   (SELECT cs.rank_position FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as rank_position,
                   (SELECT cs.tier FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as candidate_tier
            FROM molecules m
            WHERE m.project_id = :project_id
        """
        params = {"project_id": project_id}

        if search:
            query += " AND (m.name LIKE :search OR m.id LIKE :search OR m.smiles LIKE :search OR m.formula LIKE :search)"
            params["search"] = f"%{search}%"
        if lipinski_only:
            query += " AND m.lipinski_pass = 1"
        if min_mw is not None:
            query += " AND m.molecular_weight >= :min_mw"
            params["min_mw"] = min_mw
        if max_mw is not None:
            query += " AND m.molecular_weight <= :max_mw"
            params["max_mw"] = max_mw
        if min_logp is not None:
            query += " AND m.logp >= :min_logp"
            params["min_logp"] = min_logp
        if max_logp is not None:
            query += " AND m.logp <= :max_logp"
            params["max_logp"] = max_logp
        if max_docking is not None:
            query += " AND (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) <= :max_docking"
            params["max_docking"] = max_docking
        if tier and tier != 'All':
            query += " AND (SELECT cs.tier FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) = :tier"
            params["tier"] = tier

        count_query = f"SELECT COUNT(*) as cnt FROM ({query})"
        total_count = conn.execute(count_query, params).fetchone()["cnt"]

        allowed_sorts = {
            "created_at": "m.created_at",
            "name": "m.name",
            "id": "m.id",
            "molecular_weight": "m.molecular_weight",
            "logp": "m.logp",
            "tpsa": "m.tpsa",
            "qed": "m.qed",
            "docking_score": "docking_score",
            "candidate_score": "candidate_score"
        }
        col = allowed_sorts.get(sort_by, "m.created_at")
        direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        query += f" ORDER BY {col} IS NULL, {col} {direction} LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        rows = conn.execute(query, params).fetchall()
        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "molecules": [dict(r) for r in rows]
        }

def get_molecule_detail(molecule_id: str) -> Optional[dict]:
    with get_db() as conn:
        mol = conn.execute("SELECT * FROM molecules WHERE id = ?", (molecule_id,)).fetchone()
        if not mol:
            return None
        res = dict(mol)

        project = conn.execute("SELECT * FROM projects WHERE id = ?", (res["project_id"],)).fetchone()
        res["project"] = dict(project) if project else None

        dockings = conn.execute(
            "SELECT * FROM docking_results WHERE molecule_id = ? ORDER BY created_at DESC",
            (molecule_id,)
        ).fetchall()
        res["docking_results"] = [dict(d) for d in dockings]

        admets = conn.execute(
            "SELECT * FROM admet_results WHERE molecule_id = ? ORDER BY created_at DESC",
            (molecule_id,)
        ).fetchall()
        res["admet_results"] = [dict(a) for a in admets]

        cand = conn.execute(
            "SELECT * FROM candidate_scores WHERE molecule_id = ?",
            (molecule_id,)
        ).fetchone()
        res["candidate_score"] = dict(cand) if cand else None

        dsets = conn.execute(
            """
            SELECT d.*, dm.included_at
            FROM datasets d
            JOIN dataset_molecules dm ON d.id = dm.dataset_id
            WHERE dm.molecule_id = ?
            ORDER BY d.version ASC
            """,
            (molecule_id,)
        ).fetchall()
        res["datasets"] = [dict(d) for d in dsets]

        timeline = []
        first_ds = res["datasets"][0] if res["datasets"] else None
        timeline.append({
            "stage": "Imported",
            "title": "Raw Molecule Ingested & Parsed",
            "timestamp": res["created_at"],
            "experiment_id": first_ds["experiment_id"] if first_ds else None,
            "dataset_version": first_ds["version_label"] if first_ds else "v1",
            "tool": "AIDD Chemical Parser Service",
            "origin": "COMPUTED",
            "status": "completed",
            "details": f"Original SMILES: {res['original_smiles']} | SHA-256: {res.get('sha256_hash', '')[:12]}..."
        })

        if res.get("standardized_smiles") and res["standardized_smiles"] != res["original_smiles"]:
            timeline.append({
                "stage": "Preprocessing",
                "title": "Structure Standardized & Desalted",
                "timestamp": res["created_at"],
                "experiment_id": res["datasets"][1]["experiment_id"] if len(res["datasets"]) > 1 else None,
                "dataset_version": res["datasets"][1]["version_label"] if len(res["datasets"]) > 1 else "v2",
                "tool": "AIDD Standardization Kernel",
                "origin": "COMPUTED",
                "status": "completed",
                "details": f"Standardized: {res['standardized_smiles']}"
            })

        timeline.append({
            "stage": "Descriptors",
            "title": "Physicochemical & Ro5 Properties Evaluated",
            "timestamp": res["created_at"],
            "experiment_id": first_ds["experiment_id"] if first_ds else None,
            "dataset_version": first_ds["version_label"] if first_ds else "v1",
            "tool": "RDKit & Scientific Engine",
            "origin": res.get("descriptor_origin", "COMPUTED"),
            "status": "completed",
            "details": f"MW: {res['molecular_weight']} Da, LogP: {res['logp']}, TPSA: {res['tpsa']} Å², Ro5 Violations: {res['lipinski_violations']}"
        })

        for dr in res["docking_results"]:
            timeline.append({
                "stage": "Docking",
                "title": f"Molecular Docking ({dr['docking_tool']})",
                "timestamp": dr["created_at"],
                "experiment_id": dr["experiment_id"],
                "dataset_version": "v2/v3",
                "tool": f"{dr['docking_tool']}",
                "origin": dr["result_origin"],
                "status": "completed",
                "details": f"Receptor: {dr['receptor']} | Score: {dr['docking_score']} kcal/mol | Origin: {dr['result_origin']}"
            })

        for ar in res["admet_results"]:
            timeline.append({
                "stage": "ADMET",
                "title": f"In Silico ADMET Profiling ({ar.get('provider_tool', 'Consensus')})",
                "timestamp": ar["created_at"],
                "experiment_id": ar["experiment_id"],
                "dataset_version": "v3",
                "tool": ar.get("provider_tool", "ADMET Consensus"),
                "origin": ar["result_origin"],
                "status": "completed",
                "details": f"Risk: {ar['admet_risk_level']} | GI: {ar['gi_absorption']} | BBB: {ar['bbb_permeant']} | CYP3A4: {ar['cyp3a4_inhibitor']} | Origin: {ar['result_origin']}"
            })

        if res["candidate_score"]:
            cs = res["candidate_score"]
            timeline.append({
                "stage": "Candidate Selection",
                "title": f"Multi-Parameter Ranking: Rank #{cs['rank_position']} ({cs['tier']})",
                "timestamp": cs["updated_at"],
                "experiment_id": cs.get("experiment_id"),
                "dataset_version": "v4_candidates",
                "tool": "AIDD Multi-Objective Optimizer",
                "origin": cs.get("result_origin") or "UNKNOWN",
                "status": "completed",
                "details": f"Composite Score: {cs['composite_score']:.1f}/100 | Formula: {cs.get('formula_expression', 'Composite Scoring')}"
            })

        res["timeline"] = sorted(timeline, key=lambda x: x["timestamp"])

        return res

# -------------------------------------------------------------------
# DATASET VERSIONING
# -------------------------------------------------------------------

def get_project_datasets(project_id: str) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT d.*,
                   p.name as parent_dataset_name,
                   e.name as experiment_name,
                   e.tool as experiment_tool
            FROM datasets d
            LEFT JOIN datasets p ON d.parent_dataset_id = p.id
            LEFT JOIN experiments e ON d.experiment_id = e.id
            WHERE d.project_id = ?
            ORDER BY d.version ASC
            """,
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_dataset_detail(dataset_id: str) -> Optional[dict]:
    with get_db() as conn:
        ds = conn.execute(
            """
            SELECT d.*,
                   p.name as parent_dataset_name,
                   p.version_label as parent_version_label,
                   e.name as experiment_name,
                   e.tool as experiment_tool
            FROM datasets d
            LEFT JOIN datasets p ON d.parent_dataset_id = p.id
            LEFT JOIN experiments e ON d.experiment_id = e.id
            WHERE d.id = ?
            """,
            (dataset_id,)
        ).fetchone()
        if not ds:
            return None
        res = dict(ds)

        mols = conn.execute(
            """
            SELECT m.*,
                   (SELECT dr.docking_score FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_score,
                   (SELECT dr.result_origin FROM docking_results dr WHERE dr.molecule_id = m.id AND dr.project_id = m.project_id ORDER BY dr.created_at DESC LIMIT 1) as docking_origin,
                   (SELECT ar.admet_risk_level FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = m.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_risk_level,
                   (SELECT ar.result_origin FROM admet_results ar WHERE ar.molecule_id = m.id AND ar.project_id = ar.project_id ORDER BY ar.created_at DESC LIMIT 1) as admet_origin,
                   (SELECT cs.composite_score FROM candidate_scores cs WHERE cs.molecule_id = m.id AND cs.project_id = m.project_id ORDER BY cs.updated_at DESC LIMIT 1) as composite_score
            FROM molecules m
            JOIN dataset_molecules dm ON m.id = dm.molecule_id
            WHERE dm.dataset_id = ?
            ORDER BY m.id ASC
            """,
            (dataset_id,)
        ).fetchall()
        res["molecules"] = [dict(m) for m in mols]
        return res

def compare_datasets(dataset_id_1: str, dataset_id_2: str) -> dict:
    ds1 = get_dataset_detail(dataset_id_1)
    ds2 = get_dataset_detail(dataset_id_2)
    if not ds1 or not ds2:
        raise ValueError("One or both datasets not found")

    mols1_map = {m["id"]: m for m in ds1["molecules"]}
    mols2_map = {m["id"]: m for m in ds2["molecules"]}

    set1 = set(mols1_map.keys())
    set2 = set(mols2_map.keys())

    common_ids = set1.intersection(set2)
    added_ids = set2 - set1
    removed_ids = set1 - set2

    return {
        "dataset_1": {"id": ds1["id"], "version_label": ds1["version_label"], "count": len(ds1["molecules"]), "sha256": ds1.get("sha256_hash")},
        "dataset_2": {"id": ds2["id"], "version_label": ds2["version_label"], "count": len(ds2["molecules"]), "sha256": ds2.get("sha256_hash")},
        "common_count": len(common_ids),
        "added_count": len(added_ids),
        "removed_count": len(removed_ids),
        "added_molecules": [mols2_map[mid] for mid in added_ids],
        "removed_molecules": [mols1_map[mid] for mid in removed_ids]
    }

def export_dataset_csv_from_list(molecules_list: List[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "molecule_id", "molecule_name", "original_smiles", "standardized_smiles", "canonical_smiles",
        "formula", "molecular_weight", "logp", "hbd", "hba", "tpsa", "rotatable_bonds",
        "lipinski_violations", "lipinski_pass", "qed", "sha256_hash", "descriptor_origin"
    ])
    for m in molecules_list:
        writer.writerow([
            m["id"], m["name"], m.get("original_smiles", m["smiles"]), m.get("standardized_smiles", m["smiles"]),
            m.get("canonical_smiles", m["smiles"]), m.get("formula", ""),
            m.get("molecular_weight", ""), m.get("logp", ""), m.get("hbd", ""), m.get("hba", ""),
            m.get("tpsa", ""), m.get("rotatable_bonds", ""), m.get("lipinski_violations", ""),
            "PASS" if m.get("lipinski_pass") else "FAIL", m.get("qed", ""), m.get("sha256_hash", ""),
            m.get("descriptor_origin", "COMPUTED")
        ])
    return output.getvalue()

def export_dataset_csv(dataset_id: str) -> str:
    ds = get_dataset_detail(dataset_id)
    if not ds:
        raise ValueError("Dataset not found")
    return export_dataset_csv_from_list(ds["molecules"])

# -------------------------------------------------------------------
# RESEARCH DECISION LOG
# -------------------------------------------------------------------

def add_decision_log(project_id: str,
                     title: str,
                     decision_text: str,
                     rationale: str,
                     author: str = "Lead Researcher",
                     related_experiment_id: Optional[str] = None,
                     related_dataset_id: Optional[str] = None,
                     stage: Optional[str] = None) -> dict:
    dec_id = gen_id("dec")
    ts = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO decision_logs (id, project_id, title, decision_text, rationale, author, related_experiment_id, related_dataset_id, stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (dec_id, project_id, title, decision_text, rationale, author, related_experiment_id, related_dataset_id, stage, ts)
        )
    return get_decision_log(dec_id)

def get_decision_log(decision_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT dl.*,
                   e.name as related_experiment_name,
                   d.version_label as related_dataset_label
            FROM decision_logs dl
            LEFT JOIN experiments e ON dl.related_experiment_id = e.id
            LEFT JOIN datasets d ON dl.related_dataset_id = d.id
            WHERE dl.id = ?
            """,
            (decision_id,)
        ).fetchone()
        return dict(row) if row else None

def list_decision_logs(project_id: str) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT dl.*,
                   e.name as related_experiment_name,
                   d.version_label as related_dataset_label
            FROM decision_logs dl
            LEFT JOIN experiments e ON dl.related_experiment_id = e.id
            LEFT JOIN datasets d ON dl.related_dataset_id = d.id
            WHERE dl.project_id = ?
            ORDER BY dl.created_at DESC
            """,
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def delete_decision_log(decision_id: str) -> bool:
    with get_db() as conn:
        conn.execute("DELETE FROM decision_logs WHERE id = ?", (decision_id,))
    return True

# -------------------------------------------------------------------
# PROVENANCE GRAPH
# -------------------------------------------------------------------

def get_provenance_graph(project_id: str) -> dict:
    with get_db() as conn:
        datasets = conn.execute("SELECT * FROM datasets WHERE project_id = ? ORDER BY version ASC", (project_id,)).fetchall()
        experiments = conn.execute("SELECT * FROM experiments WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
        candidates = conn.execute("SELECT * FROM candidate_scores WHERE project_id = ? ORDER BY composite_score DESC LIMIT 5", (project_id,)).fetchall()
        edges_rows = conn.execute("SELECT * FROM provenance_edges WHERE project_id = ?", (project_id,)).fetchall()

    nodes = []
    for d in datasets:
        nodes.append({
            "id": d["id"],
            "type": "dataset",
            "label": d["version_label"],
            "title": d["name"],
            "subtitle": f"{d['molecule_count']} molecules",
            "stage": d["stage"],
            "version": d["version"],
            "sha256": dict(d).get("sha256_hash", ""),
            "created_at": d["created_at"],
            "status": "active"
        })

    for e in experiments:
        nodes.append({
            "id": e["id"],
            "type": "experiment",
            "label": e["name"],
            "title": f"{e['tool']} ({e['tool_version']})",
            "subtitle": f"{e['stage']} • {e['duration_seconds']}s",
            "stage": e["stage"],
            "status": e["status"],
            "is_locked": bool(dict(e).get("is_locked", 1)),
            "molecules_in": e["molecules_in"],
            "molecules_out": e["molecules_out"],
            "molecules_failed": e["molecules_failed"],
            "created_at": e["created_at"]
        })

    if candidates:
        nodes.append({
            "id": f"candidates_{project_id}",
            "type": "candidate_set",
            "label": "Top Candidates",
            "title": f"{len(candidates)} Priority Leads",
            "subtitle": "Multi-Objective Ranked",
            "stage": "Candidate Selection",
            "status": "selected",
            "created_at": candidates[0]["updated_at"]
        })

    edges = []
    for er in edges_rows:
        edges.append({
            "id": er["id"],
            "source": er["source_id"],
            "target": er["target_id"],
            "relation_type": er["relation_type"],
            "label": er["relation_type"].replace('_', ' ')
        })

    return {
        "nodes": nodes,
        "edges": edges
    }

# -------------------------------------------------------------------
# REPRODUCIBILITY REPORT DATA
# -------------------------------------------------------------------

def generate_reproducibility_report_data(project_id: str) -> dict:
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found")

    datasets = get_project_datasets(project_id)
    experiments = list_experiments(project_id)
    decisions = list_decision_logs(project_id)
    candidates = get_candidate_rankings(project_id)
    provenance = get_provenance_graph(project_id)

    with get_db() as conn:
        failures = conn.execute(
            """
            SELECT ef.*, e.name as experiment_name, e.tool
            FROM experiment_failures ef
            JOIN experiments e ON ef.experiment_id = e.id
            WHERE e.project_id = ?
            ORDER BY ef.created_at ASC
            """,
            (project_id,)
        ).fetchall()
        all_failures = [dict(f) for f in failures]

    return {
        "project": project,
        "generated_at": now_iso(),
        "system_environment": get_system_environment_info(),
        "datasets": datasets,
        "experiments": experiments,
        "all_failures": all_failures,
        "decisions": decisions,
        "candidates": candidates,
        "provenance": provenance
    }

# -------------------------------------------------------------------
# DEMO PROJECT SEEDER ("EGFR Inhibitor Discovery")
# -------------------------------------------------------------------

def seed_demo_project() -> dict:
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM projects WHERE name = 'EGFR Inhibitor Discovery'").fetchone()
        if existing:
            return {"status": "already_exists", "project_id": existing["id"]}

    proj_id = "proj_egfr_demo"
    ts1 = "2026-08-20T08:00:00Z"
    ts2 = "2026-08-20T08:30:00Z"
    ts3 = "2026-08-20T09:15:00Z"
    ts4 = "2026-08-20T10:45:00Z"
    ts5 = "2026-08-20T11:30:00Z"
    ts6 = "2026-08-20T12:00:00Z"

    compounds = [
        {"id": "LIG-001", "name": "Osimertinib (Tagrisso)", "smiles": "C=CC(=O)Nc1cc(Nc2nccc(n2)c3cn(C)c4ccccc34)c(OC)cc1N(C)CCN(C)C"},
        {"id": "LIG-002", "name": "Gefitinib (Iressa)", "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"},
        {"id": "LIG-003", "name": "Erlotinib (Tarceva)", "smiles": "COCCOC1=C(C=C2C(=C1)C(=NC=N2)NC3=CC=CC(=C3)C#C)OCCOC"},
        {"id": "LIG-004", "name": "Lapatinib (Tykerb)", "smiles": "CS(=O)(=O)CCNCC1=CC=C(O1)C2=CC=C(C=C2)NC3=NC=NC4=CC(=C(C=C34)OCC5=CC(=CC=C5)F)Cl"},
        {"id": "LIG-005", "name": "Brigatinib (Alunbrig)", "smiles": "COc1cc(Nc2ncc(Cl)c(Nc3ccccc3P(=O)(C)C)n2)ccc1N4CCN(C)CC4"},
        {"id": "LIG-006", "name": "Afatinib (Gilotrif)", "smiles": "CN(C)CC=CC(=O)Nc1cc2c(Nc3ccc(F)c(Cl)c3)ncnc2cc1OC4CCOC4"},
        {"id": "LIG-007", "name": "Dacomitinib (Vizimpro)", "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1NC(=O)C=CCN4CCCC4"},
        {"id": "LIG-008", "name": "Icotinib (Conmana)", "smiles": "C#Cc1cccc(Nc2ncnc3cc4c(cc23)OCCOCCO4)c1"},
        {"id": "LIG-009", "name": "Vandetanib (Caprelsa)", "smiles": "COc1cc2c(Nc3ccc(Br)c(F)c3)ncnc2cc1OCC4CCN(C)CC4"},
        {"id": "LIG-010", "name": "Olmutinib (Olita)", "smiles": "C=CC(=O)Nc1cc(Nc2ncc(c(n2)Sc3ccccc3)C#N)ccc1N4CCN(C)CC4"},
        {"id": "LIG-011", "name": "Mobocertinib (Exkivity)", "smiles": "CC(C)OC(=O)c1c(Nc2cc(Nc3nccc(n3)c4cn(C)c5ccccc45)c(OC)cc2N(C)CCN(C)C)cnn1C"},
        {"id": "LIG-012", "name": "Canertinib (CI-1033)", "smiles": "C=CC(=O)Nc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN4CCOCC4"},
        {"id": "LIG-013", "name": "Rociletinib (CO-1686)", "smiles": "C=CC(=O)Nc1cc(Nc2nccc(n2)Nc3ccc(cc3)N4CCN(CC4)C(C)C)c(cc1)C(F)(F)F"},
        {"id": "LIG-014", "name": "Pyrotinib", "smiles": "Cc1ccc(cc1)c2ccc(cc2)NC(=O)C=CCN3CCCC3"},
        {"id": "LIG-015", "name": "Nazartinib (EGF816)", "smiles": "C=CC(=O)Nc1cc(c(F)cc1Nc2ncc(Cl)c(n2)c3cnc4ccccc43)N5CCN(C)CC5"},
        {"id": "LIG-FAIL-01", "name": "Unstable Valence Radical (Fail Demo)", "smiles": "c1ccccc1[N+](=O)(=O)C(F)(F)(F)(F)"},
        {"id": "LIG-FAIL-02", "name": "High MW Macrolide Polymer (MW > 800 Demo)", "smiles": "CCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCC"}
    ]

    docking_benchmark = {
        "LIG-001": -9.8, "LIG-002": -9.2, "LIG-003": -8.9, "LIG-004": -10.4, "LIG-005": -9.6,
        "LIG-006": -9.4, "LIG-007": -9.1, "LIG-008": -8.7, "LIG-009": -8.8, "LIG-010": -9.5,
        "LIG-011": -9.7, "LIG-012": -9.0, "LIG-013": -9.3, "LIG-014": -8.1, "LIG-015": -9.6
    }

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, description, disease_indication, target_protein, hypothesis, current_stage, created_at, updated_at)
            VALUES (?, 'EGFR Inhibitor Discovery',
                    'Synthetic demonstration workspace for exercising dataset, docking, ADMET, ranking, and provenance plumbing. Values are DEMO data and are not scientific validation.',
                    'Non-Small Cell Lung Cancer (NSCLC)',
                    'Epidermal Growth Factor Receptor (EGFR) Kinase Domain (PDB: 1M17 / 4WKQ)',
                    'Targeting both the ATP catalytic cleft and the adjacent hydrophobic allosteric pocket with an acrylamide or optimized aminoquinazoline scaffold yields sub-nanomolar affinity while circumventing T790M/C797S gatekeeper resistance.',
                    'Candidate Selection', ?, ?)
            """,
            (proj_id, ts1, ts6)
        )

        ds1_id = "ds_egfr_v1"
        ds2_id = "ds_egfr_v2"
        ds3_id = "ds_egfr_v3"

        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, 'EGFR Raw Candidate Library v1', 1, 'EGFR_dataset_v1', NULL, NULL, 'Bundled synthetic demo library; valid molecule count is assigned after parsing.', 'Dataset', 0, 'sha256_ds_v1_egfr', ?)
            """,
            (ds1_id, proj_id, ts1)
        )
        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, 'Standardized & Lipinski Filtered v2', 2, 'EGFR_dataset_v2', ?, NULL, 'Synthetic demo subset retained after parsing/filtering.', 'Preprocessing', 0, 'sha256_ds_v2_egfr', ?)
            """,
            (ds2_id, proj_id, ds1_id, ts2)
        )
        conn.execute(
            """
            INSERT INTO datasets (id, project_id, name, version, version_label, parent_dataset_id, experiment_id, description, stage, molecule_count, sha256_hash, created_at)
            VALUES (?, ?, 'Docking Enriched Set v3', 3, 'EGFR_dataset_v3', ?, NULL, 'Synthetic DEMO docking scores attached for interface and provenance testing.', 'Docking', 0, 'sha256_ds_v3_egfr', ?)
            """,
            (ds3_id, proj_id, ds2_id, ts3)
        )

        seeded_compounds = []
        for c in compounds:
            d = ScientificEngine.calculate_descriptors(c["smiles"])
            if d["valid"]:
                svg = ScientificEngine.generate_2d_structure(c["smiles"], width=240, height=180, dark_mode=True)
                fp = ScientificEngine.generate_fingerprint(c["smiles"])
                conn.execute(
                    """
                    INSERT INTO molecules
                    (id, project_id, name, smiles, original_smiles, standardized_smiles, standardization_notes, canonical_smiles, formula, molecular_weight, exact_molecular_weight, logp, hbd, hba, tpsa, rotatable_bonds, heavy_atoms, num_rings, lipinski_violations, lipinski_pass, veber_pass, qed, sas_score, fingerprint_bits, svg_structure, descriptor_origin, sha256_hash, status, tier, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'Pre-seeded demo compound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DEMO', ?, 'active', 'Unassigned', ?)
                    """,
                    (
                        c["id"], proj_id, c["name"], c["smiles"], c["smiles"], c["smiles"],
                        d["smiles"], d["formula"], d["molecular_weight"], d.get("exact_molecular_weight", d["molecular_weight"]),
                        d["logp"], d["hbd"], d["hba"], d["tpsa"], d["rotatable_bonds"],
                        d["heavy_atoms"], d["num_rings"], d["lipinski_violations"],
                        1 if d["lipinski_pass"] else 0, 1 if d["veber_pass"] else 0, d["qed"], d["sas_score"],
                        json.dumps(fp), svg, compute_sha256(c["smiles"]), ts1
                    )
                )
                conn.execute("INSERT INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)", (ds1_id, c["id"], ts1))
                seeded_compounds.append(c)

        retained_compounds = [c for c in seeded_compounds if c["id"] in docking_benchmark]
        conn.execute(
            "UPDATE datasets SET molecule_count = ?, description = ? WHERE id = ?",
            (len(seeded_compounds), f"Bundled synthetic demo library containing {len(seeded_compounds)} successfully parsed structures.", ds1_id)
        )
        for dataset_id in (ds2_id, ds3_id):
            conn.execute("UPDATE datasets SET molecule_count = ? WHERE id = ?", (len(retained_compounds), dataset_id))

        for c in retained_compounds:
            conn.execute("INSERT INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)", (ds2_id, c["id"], ts2))
            conn.execute("INSERT INTO dataset_molecules (dataset_id, molecule_id, included_at) VALUES (?, ?, ?)", (ds3_id, c["id"], ts3))

        exp1_id = "exp_import_01"
        exp2_id = "exp_preprocess_02"
        exp3_id = "exp_docking_03"
        exp4_id = "exp_admet_04"
        exp5_id = "exp_rank_05"

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, 'Molecule Library Ingestion', 'molecule_import', 'completed', 'Dataset', NULL, ?, 'AIDD Demo Chemical Parser', 'demo-fixture-v1', ?, ?, 0.42, ?, ?, ?, 1, NULL, NULL, ?, ?, ?, ?, ?, 'Bundled synthetic demo data.', '[]', '', ?)
            """,
            (
                exp1_id, proj_id, ds1_id, ts1, ts1, len(compounds), len(seeded_compounds), len(compounds) - len(seeded_compounds),
                json.dumps(get_system_environment_info()),
                json.dumps({"source": "BundledSyntheticDemoLibrary", "sanitization": True, "generate_2d_structures": True, "result_origin": "DEMO"}),
                json.dumps({"total_imported": len(compounds), "valid_parsed": len(seeded_compounds), "failed": len(compounds) - len(seeded_compounds)}),
                f"[{ts1}] [INFO] Parsing bundled synthetic demo library\n[{ts1}] [INFO] Generated 2D display coordinates\n[{ts1}] [WARNING] {len(compounds) - len(seeded_compounds)} structures failed parsing",
                f"{len(compounds) - len(seeded_compounds)} bundled demo structures failed parsing",
                ts1
            )
        )

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, 'Standardization & MW Cutoff Filter', 'preprocessing', 'completed', 'Preprocessing', ?, ?, 'AIDD Demo Standardization Fixture', 'demo-fixture-v1', ?, ?, 0.85, ?, ?, ?, 1, NULL, NULL, ?, ?, ?, ?, ?, 'Synthetic demo filtering step.', '[]', '', ?)
            """,
            (
                exp2_id, proj_id, ds1_id, ds2_id, ts2, ts2, len(seeded_compounds), len(retained_compounds), len(seeded_compounds) - len(retained_compounds),
                json.dumps(get_system_environment_info()),
                json.dumps({"desalting": "LargestOrganicFragment", "neutralize_charges": True, "max_mw": 650.0, "max_logp": 6.8, "max_ro5_violations": 1, "result_origin": "DEMO"}),
                json.dumps({"molecules_in": len(seeded_compounds), "molecules_out": len(retained_compounds), "molecules_filtered": len(seeded_compounds) - len(retained_compounds), "result_origin": "DEMO"}),
                f"[{ts2}] [INFO] Applied synthetic demo subset rules\n[{ts2}] [INFO] Emitted dataset snapshot EGFR_dataset_v2 [Origin: DEMO]",
                f"Excluded {len(seeded_compounds) - len(retained_compounds)} demo structures",
                ts2
            )
        )

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, 'Synthetic Docking Demo', 'docking', 'completed', 'Docking', ?, ?, 'AIDD Docking Demo Fixture', 'demo-fixture-v1', ?, ?, 12.4, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', 'Synthetic scores for interface and provenance testing only.', '[]', '', ?)
            """,
            (
                exp3_id, proj_id, ds2_id, ds3_id, ts3, ts3, len(retained_compounds), len(retained_compounds),
                json.dumps(get_system_environment_info()),
                json.dumps({"fixture": "synthetic-receptor-shaped-demo", "center": [22.4, 0.8, 52.5], "box_size": [20.0, 20.0, 20.0], "result_origin": "DEMO"}),
                json.dumps({"molecules_with_demo_scores": len(retained_compounds), "result_origin": "DEMO"}),
                f"[{ts3}] [INFO] Attached synthetic docking demo scores to {len(retained_compounds)} structures [Origin: DEMO]",
                ts3
            )
        )

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, 'Synthetic ADMET Demo', 'admet', 'completed', 'ADMET', ?, NULL, 'AIDD ADMET Demo Fixture', 'demo-fixture-v1', ?, ?, 1.2, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', 'Synthetic endpoint categories for interface and provenance testing only.', '[]', '', ?)
            """,
            (
                exp4_id, proj_id, ds3_id, ts4, ts4, len(retained_compounds), len(retained_compounds),
                json.dumps(get_system_environment_info()),
                json.dumps({"fixture": "synthetic-admet-categories", "result_origin": "DEMO"}),
                json.dumps({"evaluated_molecules": len(retained_compounds), "result_origin": "DEMO"}),
                f"[{ts4}] [INFO] Attached synthetic ADMET demo categories to {len(retained_compounds)} structures [Origin: DEMO]",
                ts4
            )
        )

        weights = {"docking": 0.35, "qsar": 0.25, "admet": 0.25, "druglikeness": 0.15}
        formula_str = "Composite Score = (35.0% * Docking_Norm) + (25.0% * QSAR_pIC50_Norm) + (25.0% * ADMET_Safety) + (15.0% * QED_DrugLikeness)"
        normalization_doc = "Min-Max Inverted Docking, pIC50 QSAR, Categorical ADMET, QED"

        conn.execute(
            """
            INSERT INTO experiments
            (id, project_id, name, experiment_type, status, stage, input_dataset_id, output_dataset_id, tool, tool_version, started_at, completed_at, duration_seconds, molecules_in, molecules_out, molecules_failed, is_locked, reproduction_of_id, reproduction_match, environment_info, parameters, metrics, logs, warnings, notes, notes_log, reproducibility_manifest, created_at)
            VALUES (?, ?, 'Lead Candidate Multi-Parameter Ranking', 'candidate_ranking', 'completed', 'Candidate Selection', ?, NULL, 'AIDD Demo Multi-Objective Optimizer', 'demo-fixture-v1', ?, ?, 0.35, ?, ?, 0, 1, NULL, NULL, ?, ?, ?, ?, '', 'Composite ranking derived from synthetic DEMO inputs.', '[]', '', ?)
            """,
            (
                exp5_id, proj_id, ds3_id, ts5, ts5, len(retained_compounds), len(retained_compounds),
                json.dumps(get_system_environment_info()),
                json.dumps({"weights": weights, "formula": formula_str, "lead_threshold": 84.0, "result_origin": "DEMO"}),
                json.dumps({"ranked_demo_records": len(retained_compounds), "result_origin": "DEMO"}),
                f"[{ts5}] [INFO] Ranked {len(retained_compounds)} synthetic demo records [Origin: DEMO]",
                ts5
            )
        )

        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp1_id, ds1_id))
        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp2_id, ds2_id))
        conn.execute("UPDATE datasets SET experiment_id = ? WHERE id = ?", (exp3_id, ds3_id))

        conn.execute(
            """
            INSERT INTO experiment_failures (id, experiment_id, molecule_id, molecule_name, smiles, pipeline_stage, error_type, error_message, created_at)
            VALUES ('fail_01', ?, 'LIG-FAIL-01', 'Unstable Valence Radical (Fail Demo)', 'c1ccccc1[N+](=O)(=O)C(F)(F)(F)(F)', 'Dataset', 'ValenceError', 'Explicit valence for nitrogen exceeds standard chemical limits', ?)
            """,
            (exp1_id, ts1)
        )
        conn.execute(
            """
            INSERT INTO experiment_failures (id, experiment_id, molecule_id, molecule_name, smiles, pipeline_stage, error_type, error_message, created_at)
            VALUES ('fail_02', ?, 'LIG-FAIL-02', 'High MW Macrolide Polymer (MW > 800 Demo)', 'CCCCCCCCCCCCCCCC(=O)OCC(OC(=O)CCCCCCCCCCCCCCC)COC(=O)CCCCCCCCCCCCCCC', 'Preprocessing', 'MolecularWeightCutoff', 'MW (807.3 Da) exceeds upper drug-likeness limit of 550.0 Da', ?)
            """,
            (exp2_id, ts2)
        )

        for c in retained_compounds:
            score = docking_benchmark.get(c["id"], -9.0)
            conn.execute(
                """
                INSERT INTO docking_results (id, project_id, molecule_id, experiment_id, docking_score, result_origin, receptor, docking_tool, pose_identifier, binding_site_coords, center_x, center_y, center_z, size_x, size_y, size_z, exhaustiveness, seed, vina_version, receptor_file_hash, ligand_file_hash, rmsd_lower_bound, rmsd_upper_bound, created_at)
                VALUES (?, ?, ?, ?, ?, 'DEMO', 'Synthetic receptor fixture', 'AIDD Docking Demo Fixture', NULL, 'synthetic fixture box', 22.4, 0.8, 52.5, 20.0, 20.0, 20.0, 16, 42, 'demo-fixture-v1', 'synthetic_fixture_hash', ?, NULL, NULL, ?)
                """,
                (gen_id("dock"), proj_id, c["id"], exp3_id, score, compute_sha256(c["smiles"]), ts3)
            )

        for c in retained_compounds:
            mid = c["id"]
            if mid == "LIG-001": gi, bbb, cyp, hep, ames, herg, clr, bio, risk = "High", "Yes", "Yes", "Low Risk", "Negative", "Low Risk", 4.2, 0.55, "Low Risk"
            elif mid == "LIG-004": gi, bbb, cyp, hep, ames, herg, clr, bio, risk = "High", "No", "Yes", "Moderate Risk", "Negative", "Low Risk", 3.1, 0.55, "Moderate Risk"
            else: gi, bbb, cyp, hep, ames, herg, clr, bio, risk = "High", "No", "Yes", "Low Risk", "Negative", "Low Risk", 5.0, 0.55, "Low Risk"

            conn.execute(
                """
                INSERT INTO admet_results
                (id, project_id, molecule_id, experiment_id, result_origin, provider_tool, model_version, endpoint_name, confidence_score, units, source_file_hash, gi_absorption, bbb_permeant, cyp3a4_inhibitor, cyp2d6_inhibitor, hepatotoxicity, mutagenicity_ames, herg_inhibition, clearance_rate, bioavailability_score, admet_risk_level, risk_details, disclaimer, created_at)
                VALUES (?, ?, ?, ?, 'DEMO', 'AIDD ADMET Demo Fixture', 'demo-fixture-v1', 'DemoADMET', 0.0, 'categorical/mL/min/kg', 'synthetic_fixture_hash', ?, ?, ?, 'No', ?, ?, ?, ?, ?, ?, ?, 'Synthetic demo values; not scientific predictions.', ?)
                """,
                (
                    gen_id("admet"), proj_id, mid, exp4_id,
                    gi, bbb, cyp, hep, ames, herg, clr, bio, risk,
                    json.dumps({"gi": gi, "bbb": bbb, "cyp3a4": cyp, "hep": hep, "ames": ames, "herg": herg}),
                    ts4
                )
            )

        candidate_tiers = [
            ("LIG-001", 91.4, 1, "Lead Candidate"),
            ("LIG-004", 88.6, 2, "Lead Candidate"),
            ("LIG-005", 87.2, 3, "Lead Candidate"),
            ("LIG-011", 86.8, 4, "Lead Candidate"),
            ("LIG-002", 84.5, 5, "Lead Candidate"),
            ("LIG-006", 83.2, 6, "Backup Lead"),
            ("LIG-015", 82.9, 7, "Backup Lead"),
            ("LIG-010", 81.7, 8, "Backup Lead"),
            ("LIG-003", 80.4, 9, "Backup Lead"),
            ("LIG-007", 79.1, 10, "Backup Lead"),
            ("LIG-013", 77.5, 11, "Follow-up"),
            ("LIG-009", 76.8, 12, "Follow-up"),
            ("LIG-012", 75.3, 13, "Follow-up"),
            ("LIG-008", 74.2, 14, "Follow-up"),
            ("LIG-014", 68.0, 15, "Follow-up")
        ]

        retained_ids = {c["id"] for c in retained_compounds}
        for mid, score, rank, tier in candidate_tiers:
            if mid not in retained_ids:
                continue
            raw_c = {"docking_raw_kcal_mol": docking_benchmark.get(mid, -9.0), "admet_raw": "Low Risk"}
            weighted_c = {"docking_contrib": 32.0, "qsar_contrib": 24.0, "admet_contrib": 24.0, "qed_contrib": 11.4}
            conn.execute(
                """
                INSERT INTO candidate_scores
                (id, project_id, molecule_id, experiment_id, composite_score, result_origin, docking_component, qsar_component, admet_component, druglikeness_component, weights_applied, formula_expression, normalization_method, raw_components_json, weighted_components_json, missing_data_policy, is_data_complete, rank_position, tier, selection_notes, updated_at)
                VALUES (?, ?, ?, ?, ?, 'DEMO', 92.0, 88.0, 95.0, 75.0, ?, ?, ?, ?, ?, 'RENORMALIZE', 1, ?, ?, ?, ?)
                """,
                (
                    gen_id("cand"), proj_id, mid, exp5_id, score,
                    json.dumps(weights), formula_str, normalization_doc,
                    json.dumps(raw_c), json.dumps(weighted_c),
                    rank, tier,
                    f"Selected as {tier} for in vitro enzymatic assay validation against mutant EGFR.",
                    ts5
                )
            )
            conn.execute("UPDATE molecules SET tier = ? WHERE id = ?", (tier, mid))

        conn.execute(
            """
            INSERT INTO decision_logs (id, project_id, title, decision_text, rationale, author, related_experiment_id, related_dataset_id, stage, created_at)
            VALUES ('dec_01', ?, 'MW Upper Limit Set to 550 Da',
                    'Filtered out compounds with MW > 650 Da during standardization preprocessing.',
                    'Kinase inhibitor bioavailability decreases sharply above 550 Da; eliminates high-MW polymeric structures while preserving targeted covalent aminoquinazolines.',
                    'Lead Medicinal Chemist', 'exp_preprocess_02', 'ds_egfr_v1', 'Preprocessing', ?)
            """,
            (proj_id, ts2)
        )
        conn.execute(
            """
            INSERT INTO decision_logs (id, project_id, title, decision_text, rationale, author, related_experiment_id, related_dataset_id, stage, created_at)
            VALUES ('dec_02', ?, 'Docking Grid Focused on C797S Mutated Cleft',
                    'Centered receptor grid on alpha-C of residue 797 with 20 Å bounding cube in 4WKQ crystal structure.',
                    'Ensures direct sampling of the mutated allosteric sub-pocket to test covalent and non-covalent binding poses simultaneously.',
                    'Lead CADD Scientist', 'exp_docking_03', 'ds_egfr_v2', 'Docking', ?)
            """,
            (proj_id, ts3)
        )
        conn.execute(
            """
            INSERT INTO decision_logs (id, project_id, title, decision_text, rationale, author, related_experiment_id, related_dataset_id, stage, created_at)
            VALUES ('dec_03', ?, 'Prioritize Once-Daily Oral Leads with BBB Permeability',
                    'Assigned top tier to Osimertinib and Brigatinib over high-MW analogues.',
                    'Non-small cell lung cancer with EGFR mutations has ~30% brain metastasis rate; BBB penetrance is essential for CNS efficacy in clinical progression.',
                    'Principal Investigator', 'exp_rank_05', 'ds_egfr_v3', 'Candidate Selection', ?)
            """,
            (proj_id, ts5)
        )

        provenance_chain = [
            ("exp_import_01", "experiment", "ds_egfr_v1", "dataset", "generated_from"),
            ("ds_egfr_v1", "dataset", "exp_preprocess_02", "experiment", "processed_by"),
            ("exp_preprocess_02", "experiment", "ds_egfr_v2", "dataset", "generated_from"),
            ("ds_egfr_v2", "dataset", "exp_docking_03", "experiment", "processed_by"),
            ("exp_docking_03", "experiment", "ds_egfr_v3", "dataset", "generated_from"),
            ("ds_egfr_v3", "dataset", "exp_admet_04", "experiment", "processed_by"),
            ("ds_egfr_v3", "dataset", "exp_rank_05", "experiment", "processed_by"),
            ("exp_rank_05", "experiment", f"candidates_{proj_id}", "candidate_set", "selected_from")
        ]

        for src, src_t, tgt, tgt_t, rel in provenance_chain:
            conn.execute(
                """
                INSERT INTO provenance_edges (id, project_id, source_id, source_type, target_id, target_type, relation_type, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)
                """,
                (gen_id("edge"), proj_id, src, src_t, tgt, tgt_t, rel, ts5)
            )

    return {"status": "seeded", "project_id": proj_id}


# Backward compatibility alias
run_preprocessing_experiment = run_standardization_experiment
