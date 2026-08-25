"""
AIDD Worker - In-Process Bounded Job Queue & Graceful Cancellation (v1.4.0)
"""

import os
import json
import time
import uuid
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from aidd_worker import config
from aidd_worker.models import (
    JobStatus, JobType, JobResult, FailureRecord, ArtifactInfo,
    DescriptorJobRequest, StandardizeJobRequest, DockingJobRequest
)
from aidd_worker.services.capability_service import detect_rdkit, detect_vina
from aidd_worker.services.environment_service import capture_full_environment
from aidd_worker.services.rdkit_service import calculate_descriptors_batch, standardize_molecules_batch
from aidd_worker.services.vina_service import execute_docking_job
from aidd_worker.services.artifact_service import save_job_artifact, create_checksum_manifest, compute_sha256

_JOBS_LOCK = threading.Lock()
_JOBS_REGISTRY: Dict[str, JobResult] = {}
_ACTIVE_SUBPROCESSES: Dict[str, Any] = {}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def gen_job_id(prefix: str = "job") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def save_job_to_disk(job: JobResult):
    job_dir = os.path.join(config.JOBS_DIR, job.job_id)
    os.makedirs(job_dir, exist_ok=True)
    manifest_path = os.path.join(job_dir, "job_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(job.model_dump_json(indent=2))

def get_job(job_id: str) -> Optional[JobResult]:
    with _JOBS_LOCK:
        if job_id in _JOBS_REGISTRY:
            return _JOBS_REGISTRY[job_id]
    
    # Check disk
    manifest_path = os.path.join(config.JOBS_DIR, job_id, "job_manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            job = JobResult(**data)
            with _JOBS_LOCK:
                _JOBS_REGISTRY[job_id] = job
            return job
    return None

def list_jobs() -> List[JobResult]:
    with _JOBS_LOCK:
        return list(_JOBS_REGISTRY.values())

def cancel_job(job_id: str, reason: str = "User cancellation request") -> Optional[JobResult]:
    job = get_job(job_id)
    if not job:
        return None

    with _JOBS_LOCK:
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            return job

        # Terminate any running subprocess
        proc = _ACTIVE_SUBPROCESSES.get(job_id)
        if proc:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass
            _ACTIVE_SUBPROCESSES.pop(job_id, None)

        job.status = JobStatus.CANCELLED
        job.completed_at = now_iso()
        job.failure_reason = reason
        job.stderr += f"\n[CANCELLED] {reason}"
        save_job_to_disk(job)

    return job

def run_descriptor_job(request: DescriptorJobRequest) -> JobResult:
    job_id = gen_job_id("job_desc")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    env_meta = capture_full_environment()
    rdkit_info = detect_rdkit()
    tool_name = "RDKit" if rdkit_info["installed"] else "AIDD Python Reference Engine (Non-Production Fallback)"
    tool_ver = rdkit_info["version"] or "1.4.0"
    mode = "NATIVE" if rdkit_info["installed"] else "DEMO_FALLBACK"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.DESCRIPTORS,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID,
        worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=rdkit_info["installed"],
        execution_mode=mode,
        environment_sha256=env_meta["environment_sha256"],
        created_at=created_at,
        started_at=started_at,
        parameters={"total_molecules": len(request.molecules), "execution_mode": mode}
    )
    with _JOBS_LOCK:
        _JOBS_REGISTRY[job_id] = job

    try:
        successful, failures, meta = calculate_descriptors_batch(request.molecules)
        duration = round(time.time() - start_time, 3)
        completed_at = now_iso()

        results_json = json.dumps(successful, indent=2)
        results_art = save_job_artifact(job_id, "descriptors_output.json", results_json, file_type="json")
        artifacts = [results_art]
        
        if failures:
            failures_json = json.dumps([f.dict() for f in failures], indent=2)
            fail_art = save_job_artifact(job_id, "failures.json", failures_json, file_type="json")
            artifacts.append(fail_art)

        chk_art = create_checksum_manifest(job_id, artifacts)
        artifacts.append(chk_art)

        with _JOBS_LOCK:
            job.status = JobStatus.COMPLETED if successful else JobStatus.FAILED
            job.completed_at = completed_at
            job.duration_seconds = duration
            job.successful_count = len(successful)
            job.failed_count = len(failures)
            job.failures = failures
            job.artifacts = artifacts
            job.results = successful
            job.metrics = {
                "molecules_processed": len(request.molecules),
                "success_rate": f"{round((len(successful)/max(1, len(request.molecules)))*100, 1)}%",
                "duration_seconds": duration
            }
            job.stdout = f"[{completed_at}] [INFO] Computed properties for {len(successful)} molecules using {tool_name}."
            job.reproducibility_hash = meta.get("reproducibility_hash") or compute_sha256(results_json)

    except Exception as e:
        with _JOBS_LOCK:
            job.status = JobStatus.FAILED
            job.completed_at = now_iso()
            job.duration_seconds = round(time.time() - start_time, 3)
            job.stderr = str(e)
            job.failure_reason = str(e)
            job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="DescriptorJobException", error_message=str(e)))

    save_job_to_disk(job)
    return job

def run_standardize_job(request: StandardizeJobRequest) -> JobResult:
    job_id = gen_job_id("job_std")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    env_meta = capture_full_environment()
    rdkit_info = detect_rdkit()
    tool_name = "RDKit Standardizer" if rdkit_info["installed"] else "AIDD Standardization Kernel (Non-Production Fallback)"
    tool_ver = rdkit_info["version"] or "1.4.0"
    mode = "NATIVE" if rdkit_info["installed"] else "DEMO_FALLBACK"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.STANDARDIZE,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID,
        worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=rdkit_info["installed"],
        execution_mode=mode,
        environment_sha256=env_meta["environment_sha256"],
        created_at=created_at,
        started_at=started_at,
        parameters={
            "profile": request.profile,
            "remove_salts": request.remove_salts,
            "neutralize": request.neutralize_charges
        }
    )
    with _JOBS_LOCK:
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

        with _JOBS_LOCK:
            job.status = JobStatus.COMPLETED if successful else JobStatus.FAILED
            job.completed_at = completed_at
            job.duration_seconds = duration
            job.successful_count = len(successful)
            job.failed_count = len(failures)
            job.failures = failures
            job.artifacts = artifacts
            job.results = successful
            job.metrics = {
                "molecules_processed": len(request.molecules),
                "retention_rate": f"{round((len(successful)/max(1, len(request.molecules)))*100, 1)}%",
                "duration_seconds": duration
            }
            job.stdout = f"[{completed_at}] [INFO] Standardization completed for {len(successful)} molecules."
            job.reproducibility_hash = compute_sha256(results_json)

    except Exception as e:
        with _JOBS_LOCK:
            job.status = JobStatus.FAILED
            job.completed_at = now_iso()
            job.duration_seconds = round(time.time() - start_time, 3)
            job.stderr = str(e)
            job.failure_reason = str(e)
            job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="StandardizationException", error_message=str(e)))

    save_job_to_disk(job)
    return job

def run_docking_job(request: DockingJobRequest) -> JobResult:
    job_id = gen_job_id("job_dock")
    created_at = now_iso()
    start_time = time.time()
    started_at = now_iso()

    env_meta = capture_full_environment()
    vina_info = detect_vina()
    vina_verified = bool(vina_info.get("installed") and vina_info.get("identity_verified"))
    tool_name = "AutoDock Vina" if vina_verified else "AIDD Vina-table demo fixture"
    tool_ver = vina_info.get("version") or "demo-fixture-v1"
    mode = "NATIVE" if vina_verified else "DEMO_FALLBACK"

    job = JobResult(
        job_id=job_id,
        status=JobStatus.RUNNING,
        job_type=JobType.DOCKING,
        experiment_id=request.experiment_id,
        worker_id=config.WORKER_ID,
        worker_version=config.WORKER_VERSION,
        tool=tool_name,
        tool_version=tool_ver,
        production_ready=vina_verified,
        execution_mode=mode,
        environment_sha256=env_meta["environment_sha256"],
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
    with _JOBS_LOCK:
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

        with _JOBS_LOCK:
            native_success = bool(
                results
                and not failures
                and meta.get("exit_code") == 0
                and meta.get("vina_identity_verified") is True
                and all(result.get("result_origin") == "COMPUTED" for result in results)
            )
            demo_success = bool(
                results
                and not failures
                and all(result.get("result_origin") == "DEMO" for result in results)
            )
            job.status = JobStatus.COMPLETED if (native_success or demo_success) else JobStatus.FAILED
            job.completed_at = completed_at
            job.duration_seconds = duration
            job.successful_count = len(results)
            job.failed_count = len(failures)
            job.failures = failures
            job.artifacts = artifacts
            job.results = results
            job.stdout = meta.get("stdout", "")
            job.stderr = meta.get("stderr", "")
            job.exit_code = meta.get("exit_code")
            job.tool = meta.get("tool") or tool_name
            job.tool_version = meta.get("tool_version") or tool_ver
            job.production_ready = bool(meta.get("production_ready"))
            job.execution_mode = "NATIVE" if native_success else "DEMO_FALLBACK"
            job.metrics = {
                "ligands_docked": len(results),
                "best_affinity_kcal_mol": min([r["best_affinity_kcal_mol"] for r in results]) if results else 0.0,
                "duration_seconds": duration,
                "exit_code": meta.get("exit_code"),
                "worker_id": config.WORKER_ID,
                "tool": job.tool,
                "tool_version": job.tool_version,
                "vina_identity_verified": meta.get("vina_identity_verified", False),
                "vina_binary_sha256": meta.get("vina_binary_sha256"),
                "vina_version_output_sha256": meta.get("vina_version_output_sha256"),
                "stdout_sha256": meta.get("stdout_sha256"),
                "stderr_sha256": meta.get("stderr_sha256"),
                "receptor_sha256": meta.get("receptor_sha256"),
                "output_pdbqt_hashes": meta.get("output_pdbqt_hashes", []),
            }
            job.reproducibility_hash = meta.get("reproducibility_hash") or compute_sha256(results_json)

    except Exception as e:
        with _JOBS_LOCK:
            job.status = JobStatus.FAILED
            job.completed_at = now_iso()
            job.duration_seconds = round(time.time() - start_time, 3)
            job.stderr = str(e)
            job.failure_reason = str(e)
            job.failures.append(FailureRecord(molecule_id="JOB_FATAL", error_type="DockingJobException", error_message=str(e)))

    save_job_to_disk(job)
    return job
