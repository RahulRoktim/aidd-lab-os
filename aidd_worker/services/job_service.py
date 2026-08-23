"""
AIDD Worker - Formal Scientific Job System & Execution Manager
"""

import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from aidd_worker import config
from aidd_worker.models import (
    JobStatus, JobType, JobResult, FailureRecord, ArtifactInfo,
    DescriptorJobRequest, StandardizeJobRequest, DockingJobRequest
)
from aidd_worker.services.capability_service import detect_rdkit, detect_vina
from aidd_worker.services.rdkit_service import calculate_descriptors_batch, standardize_molecules_batch
from aidd_worker.services.vina_service import execute_docking_job
from aidd_worker.services.artifact_service import save_job_artifact, create_checksum_manifest, compute_sha256

# In-memory registry of executed jobs (persisted to disk in jobs_data/{job_id}/)
_JOBS_REGISTRY: Dict[str, JobResult] = {}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def gen_job_id(prefix: str = "job") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def save_job_to_disk(job: JobResult):
    job_dir = os.path.join(config.JOBS_DIR, job.job_id)
    os.makedirs(job_dir, exist_ok=True)
    manifest_path = os.path.join(job_dir, "job_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(job.json(indent=2))

def get_job(job_id: str) -> Optional[JobResult]:
    if job_id in _JOBS_REGISTRY:
        return _JOBS_REGISTRY[job_id]
    
    # Try reading from disk
    manifest_path = os.path.join(config.JOBS_DIR, job_id, "job_manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            job = JobResult(**data)
            _JOBS_REGISTRY[job_id] = job
            return job
    return None

def list_jobs() -> List[JobResult]:
    return list(_JOBS_REGISTRY.values())

def run_descriptor_job(request: DescriptorJobRequest) -> JobResult:
    job_id = gen_job_id("job_desc")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    rdkit_info = detect_rdkit()
    tool_name = "RDKit" if rdkit_info["installed"] else "AIDD Python Reference Engine (Non-Production Fallback)"
    tool_ver = rdkit_info["version"] or "1.3.0"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.DESCRIPTORS,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID, worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=rdkit_info["installed"],
        created_at=created_at,
        started_at=started_at,
        parameters={"total_molecules": len(request.molecules)}
    )
    _JOBS_REGISTRY[job_id] = job

    try:
        successful, failures, meta = calculate_descriptors_batch(request.molecules)
        duration = round(time.time() - start_time, 3)
        completed_at = now_iso()

        # Save artifacts
        results_json = json.dumps(successful, indent=2)
        results_art = save_job_artifact(job_id, "descriptors_output.json", results_json, file_type="json")
        
        artifacts = [results_art]
        if failures:
            failures_json = json.dumps([f.dict() for f in failures], indent=2)
            fail_art = save_job_artifact(job_id, "failures.json", failures_json, file_type="json")
            artifacts.append(fail_art)

        chk_art = create_checksum_manifest(job_id, artifacts)
        artifacts.append(chk_art)

        job.status = JobStatus.COMPLETED if successful else JobStatus.FAILED
        job.completed_at = completed_at
        job.duration_seconds = duration
        job.successful_count = len(successful)
        job.failed_count = len(failures)
        job.failures = failures
        job.artifacts = artifacts
        job.results = successful
        job.exit_code = meta.get("exit_code", 0)
        job.metrics = {
            "molecules_processed": len(request.molecules),
            "success_rate": f"{round((len(successful)/max(1, len(request.molecules)))*100, 1)}%",
            "duration_seconds": duration
        }
        job.stdout = f"[{completed_at}] [INFO] Descriptors calculated for {len(successful)} molecules using {tool_name}."
        job.reproducibility_hash = compute_sha256(results_json)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.completed_at = now_iso()
        job.duration_seconds = round(time.time() - start_time, 3)
        job.stderr = str(e)
        job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="JobExecutionException", error_message=str(e)))

    save_job_to_disk(job)
    return job

def run_standardize_job(request: StandardizeJobRequest) -> JobResult:
    job_id = gen_job_id("job_std")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    rdkit_info = detect_rdkit()
    tool_name = "RDKit Standardizer" if rdkit_info["installed"] else "AIDD Standardization Kernel (Non-Production Fallback)"
    tool_ver = rdkit_info["version"] or "1.3.0"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.STANDARDIZE,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID, worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=rdkit_info["installed"],
        created_at=created_at,
        started_at=started_at,
        parameters={"remove_salts": request.remove_salts, "neutralize": request.neutralize_charges}
    )
    _JOBS_REGISTRY[job_id] = job

    try:
        successful, failures, meta = standardize_molecules_batch(
            request.molecules,
            remove_salts=request.remove_salts if request.remove_salts is not None else True,
            neutralize=request.neutralize_charges if request.neutralize_charges is not None else True
        )
        duration = round(time.time() - start_time, 3)
        completed_at = now_iso()

        results_json = json.dumps(successful, indent=2)
        results_art = save_job_artifact(job_id, "standardized_output.json", results_json, file_type="json")
        artifacts = [results_art]
        
        if failures:
            fail_art = save_job_artifact(job_id, "failures.json", json.dumps([f.dict() for f in failures], indent=2), file_type="json")
            artifacts.append(fail_art)

        chk_art = create_checksum_manifest(job_id, artifacts)
        artifacts.append(chk_art)

        job.status = JobStatus.COMPLETED if successful else JobStatus.FAILED
        job.completed_at = completed_at
        job.duration_seconds = duration
        job.successful_count = len(successful)
        job.failed_count = len(failures)
        job.failures = failures
        job.artifacts = artifacts
        job.results = successful
        job.exit_code = meta.get("exit_code", 0)
        job.metrics = {
            "molecules_processed": len(request.molecules),
            "retention_rate": f"{round((len(successful)/max(1, len(request.molecules)))*100, 1)}%",
            "duration_seconds": duration
        }
        job.stdout = f"[{completed_at}] [INFO] Standardization completed for {len(successful)} molecules."
        job.reproducibility_hash = compute_sha256(results_json)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.completed_at = now_iso()
        job.duration_seconds = round(time.time() - start_time, 3)
        job.stderr = str(e)
        job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="StandardizationJobException", error_message=str(e)))

    save_job_to_disk(job)
    return job

def run_docking_job(request: DockingJobRequest) -> JobResult:
    job_id = gen_job_id("job_dock")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    vina_info = detect_vina()
    tool_name = vina_info["version"] or "AutoDock Vina"
    tool_ver = "1.2.5"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.DOCKING,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID, worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=vina_info["installed"],
        created_at=created_at,
        started_at=started_at,
        parameters={
            "receptor": request.receptor_name,
            "search_box": request.search_box.dict(),
            "exhaustiveness": request.exhaustiveness or 16,
            "num_modes": request.num_modes or 9,
            "seed": request.seed or 42
        }
    )
    _JOBS_REGISTRY[job_id] = job

    try:
        results, failures, artifacts, meta = execute_docking_job(job_id, request)
        duration = round(time.time() - start_time, 3)
        completed_at = now_iso()

        results_json = json.dumps(results, indent=2)
        results_art = save_job_artifact(job_id, "docking_results.json", results_json, file_type="json")
        artifacts.append(results_art)

        chk_art = create_checksum_manifest(job_id, artifacts)
        artifacts.append(chk_art)

        job.status = JobStatus.COMPLETED if results else JobStatus.FAILED
        job.completed_at = completed_at
        job.duration_seconds = duration
        job.successful_count = len(results)
        job.failed_count = len(failures)
        job.failures = failures
        job.artifacts = artifacts
        job.results = results
        job.stdout = meta.get("stdout", "")
        job.stderr = meta.get("stderr", "")
        job.exit_code = meta.get("exit_code", 0)
        job.metrics = {
            "ligands_docked": len(results),
            "best_affinity_kcal_mol": min([r["best_affinity_kcal_mol"] for r in results]) if results else 0.0,
            "duration_seconds": duration
        }
        job.reproducibility_hash = compute_sha256(results_json)

    except Exception as e:
        job.status = JobStatus.FAILED
        job.completed_at = now_iso()
        job.duration_seconds = round(time.time() - start_time, 3)
        job.stderr = str(e)
        job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="DockingJobExecutionException", error_message=str(e)))

    save_job_to_disk(job)
    return job
