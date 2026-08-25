"""
AIDD Worker - FastAPI Scientific Execution Service (v1.4.0)
Exposes REST endpoints for health, readiness, capability discovery,
native RDKit / AutoDock Vina execution, bounded queue tracking, and artifact retrieval.
"""

import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from aidd_worker import config
from aidd_worker.models import (
    DescriptorJobRequest, StandardizeJobRequest, DockingJobRequest,
    JobResult, JobStatus, ReadinessResponse
)
from aidd_worker.services.capability_service import get_all_capabilities, detect_rdkit, detect_vina, detect_openbabel
from aidd_worker.services.environment_service import capture_full_environment
from aidd_worker.services.rdkit_service import run_50_molecule_validation_suite
from aidd_worker.services import job_queue_service

app = FastAPI(
    title="AIDD Scientific Worker API",
    description="Dedicated Local Worker for Native Cheminformatics & Molecular Docking Execution",
    version=config.WORKER_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------
# WORKER HEALTH, READINESS & CAPABILITIES
# -----------------------------------------------------------------

@app.get("/health")
async def get_health():
    """
    Basic process liveness check. Returns OK if the worker HTTP process is running.
    """
    caps = get_all_capabilities()
    return {
        "status": "OK",
        "worker_id": config.WORKER_ID,
        "worker_version": config.WORKER_VERSION,
        "hostname": caps["platform"]["hostname"],
        "os": caps["platform"]["system"],
        "architecture": caps["platform"]["architecture"],
        "active_jobs_count": len([j for j in job_queue_service.list_jobs() if j.status == JobStatus.RUNNING]),
        "total_jobs_completed": len([j for j in job_queue_service.list_jobs() if j.status == JobStatus.COMPLETED])
    }

@app.get("/readiness", response_model=ReadinessResponse)
async def get_readiness():
    """
    Scientific readiness check. Evaluates whether production dependencies (RDKit, Vina) exist.
    """
    rdk = detect_rdkit()
    vina = detect_vina()
    ob = detect_openbabel()
    env = capture_full_environment()

    vina_verified = bool(vina.get("installed") and vina.get("identity_verified"))
    is_fully_ready = rdk["installed"] and vina_verified
    status_str = "READY" if is_fully_ready else ("DEGRADED" if rdk["installed"] or vina["installed"] else "UNAVAILABLE")

    return ReadinessResponse(
        status=status_str,
        health="OK",
        worker_version=config.WORKER_VERSION,
        worker_id=config.WORKER_ID,
        api_version=config.API_VERSION,
        rdkit_ready=rdk["installed"],
        rdkit_version=rdk["version"],
        rdkit_backend=rdk["backend"],
        vina_ready=vina_verified,
        vina_version=vina["version"],
        vina_path=vina["path"],
        vina_identity_verified=vina.get("identity_verified", False),
        vina_binary_sha256=vina.get("binary_sha256"),
        vina_version_output_sha256=vina.get("version_output_sha256"),
        openbabel_ready=ob["installed"],
        environment_sha256=env["environment_sha256"],
        diagnostics={
            "jobs_storage_writable": os.access(config.JOBS_DIR, os.W_OK),
            "artifacts_storage_writable": os.access(config.ARTIFACTS_DIR, os.W_OK),
            "cpu_cores": env["cpu_cores"],
            "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS
        }
    )

@app.get("/capabilities")
async def get_capabilities():
    return get_all_capabilities()

@app.get("/environment")
async def get_environment():
    return capture_full_environment()

@app.get("/validation/rdkit")
async def validate_rdkit_benchmark():
    return run_50_molecule_validation_suite()

# -----------------------------------------------------------------
# JOB EXECUTION ENDPOINTS
# -----------------------------------------------------------------

@app.post("/jobs/descriptors", response_model=JobResult)
async def submit_descriptor_job(request: DescriptorJobRequest):
    if not request.molecules:
        raise HTTPException(status_code=400, detail="Molecule list cannot be empty")
    return job_queue_service.run_descriptor_job(request)

@app.post("/jobs/standardize", response_model=JobResult)
async def submit_standardize_job(request: StandardizeJobRequest):
    if not request.molecules:
        raise HTTPException(status_code=400, detail="Molecule list cannot be empty")
    return job_queue_service.run_standardize_job(request)

@app.post("/jobs/docking", response_model=JobResult)
async def submit_docking_job(request: DockingJobRequest):
    if not request.receptor_pdbqt.strip():
        raise HTTPException(status_code=400, detail="Receptor PDBQT structure is required")
    if not request.ligands:
        raise HTTPException(status_code=400, detail="At least one ligand is required for docking")
    return job_queue_service.run_docking_job(request)

@app.get("/jobs", response_model=List[JobResult])
async def list_jobs():
    return job_queue_service.list_jobs()

@app.get("/jobs/{job_id}", response_model=JobResult)
async def get_job_status(job_id: str):
    job = job_queue_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/jobs/{job_id}/cancel", response_model=JobResult)
async def cancel_job(job_id: str):
    job = job_queue_service.cancel_job(job_id, reason="User cancellation request via API")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/jobs/{job_id}/artifacts/{filename}")
async def get_job_artifact(job_id: str, filename: str):
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(config.JOBS_DIR, job_id, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(file_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
