import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from aidd_worker import config
from aidd_worker.models import DescriptorJobRequest, JobResult, JobStatus
from aidd_worker.services import job_queue_service as queue
from aidd_worker.services import artifact_service


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "JOBS_DIR", str(tmp_path))
    queue._JOBS_REGISTRY.clear()
    yield
    queue._JOBS_REGISTRY.clear()


def job(status=JobStatus.RUNNING):
    return JobResult(job_id="job_recover", status=status, job_type="descriptors",
                     worker_id="test", tool="synthetic", tool_version="1",
                     production_ready=False, created_at="2026-09-11T00:00:00Z")


def test_restart_marks_interrupted_and_loads_history(tmp_path):
    queue.save_job_to_disk(job())
    evidence = tmp_path / "job_recover" / "input.txt"
    evidence.write_text("preserve me")
    queue.recover_jobs()
    recovered = queue.list_jobs()[0]
    assert recovered.status == JobStatus.FAILED
    assert "INTERRUPTED" in recovered.failure_reason
    assert evidence.read_text() == "preserve me"
    queue._JOBS_REGISTRY.clear()
    queue.recover_jobs()
    assert queue.list_jobs()[0].status == JobStatus.FAILED


def test_corrupt_manifest_stops_recovery_without_overwriting(tmp_path):
    directory = tmp_path / "job_bad"
    directory.mkdir()
    manifest = directory / "job_manifest.json"
    manifest.write_text("{broken")
    with pytest.raises(RuntimeError, match="preserved"):
        queue.recover_jobs()
    assert manifest.read_text() == "{broken"


def test_atomic_artifact_failure_preserves_previous_bytes(monkeypatch, tmp_path):
    artifact_service.save_job_artifact("job_atomic", "result.txt", "original")
    def disk_failure(*args):
        raise OSError("injected replace failure")
    monkeypatch.setattr(artifact_service.os, "replace", disk_failure)
    with pytest.raises(OSError):
        artifact_service.save_job_artifact("job_atomic", "result.txt", "replacement")
    assert (tmp_path / "job_atomic" / "result.txt").read_text() == "original"


def test_running_manifest_and_cooperative_cancel_are_truthful(monkeypatch, tmp_path):
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(queue, "capture_full_environment", lambda: {"environment_sha256": "test"})
    monkeypatch.setattr(queue, "detect_rdkit", lambda: {"installed": False, "version": None})
    def calculation(molecules):
        entered.set()
        assert release.wait(10)
        return [{"id": "one"}], [], {}
    monkeypatch.setattr(queue, "calculate_descriptors_batch", calculation)
    result = []
    thread = threading.Thread(target=lambda: result.append(queue.run_descriptor_job(
        DescriptorJobRequest(molecules=[{"id":"one", "smiles":"CCO"}], execution_mode="DEMO_FALLBACK"))))
    thread.start()
    try:
        assert entered.wait(10)
        current = queue.list_jobs()[0]
        persisted = json.loads((tmp_path/current.job_id/"job_manifest.json").read_text())
        assert persisted["status"] == "RUNNING"
        cancelled = queue.cancel_job(current.job_id)
        assert cancelled.status == JobStatus.RUNNING
        assert cancelled.parameters["cancel_requested"] is True
    finally:
        release.set()
        thread.join(10)
    assert result[0].status == JobStatus.CANCELLED
    assert result[0].results is None
    assert result[0].production_ready is False
    persisted = json.loads((tmp_path/result[0].job_id/"job_manifest.json").read_text())
    assert persisted["status"] == "CANCELLED"


def test_capacity_rejects_before_creating_job(monkeypatch):
    gate = threading.BoundedSemaphore(1)
    monkeypatch.setattr(queue, "_CAPACITY", gate)
    gate.acquire()
    try:
        with pytest.raises(queue.QueueCapacityError):
            queue.run_descriptor_job(DescriptorJobRequest(molecules=[]))
        assert queue.list_jobs() == []
    finally:
        gate.release()


def test_worker_blocks_foreign_origin_and_host():
    from aidd_worker.main import app
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/jobs", headers={"Origin":"https://evil.example"}).status_code == 403
        assert client.get("/jobs", headers={"Host":"evil.example"}).status_code == 400
        assert client.get("/jobs", headers={"Origin":"http://localhost:8000"}).status_code == 200


def test_nonfinite_box_rejected():
    from aidd_worker.models import SearchBoxConfig
    with pytest.raises(ValueError):
        SearchBoxConfig(center_x=float("nan"),center_y=0,center_z=0)


def test_post_body_survives_boundary_and_oversize_is_rejected(monkeypatch):
    from aidd_worker.main import app
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post('/jobs/descriptors', json={'molecules': []})
        assert response.status_code == 400
        monkeypatch.setattr(config, 'MAX_UPLOAD_SIZE_BYTES', 8)
        assert client.post('/jobs/descriptors', content=b'x'*9).status_code == 413


def test_tampered_artifact_is_not_downloadable(tmp_path):
    from aidd_worker.main import app
    current = job(JobStatus.COMPLETED)
    current.artifacts = [artifact_service.save_job_artifact(current.job_id, 'output.json', '{}')]
    queue.save_job_to_disk(current)
    (tmp_path/current.job_id/'output.json').write_text('{"forged":true}')
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get(f'/jobs/{current.job_id}/artifacts/output.json').status_code == 409


def test_app_startup_uses_isolated_database_without_demo_seeding(monkeypatch, tmp_path):
    from app import database
    from app.main import app
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path/'new.db'))
    monkeypatch.delenv('AIDD_SEED_DEMO', raising=False)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.get('/api/projects').status_code == 200
        assert client.get('/api/projects', headers={'Origin':'https://evil.example'}).status_code == 403
    with database.get_db() as connection:
        assert connection.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 0


def test_requested_native_rdkit_does_not_silently_fallback(monkeypatch):
    monkeypatch.setattr(queue, 'capture_full_environment', lambda: {'environment_sha256':'test'})
    monkeypatch.setattr(queue, 'detect_rdkit', lambda: {'installed':True,'production_ready':False,'version':'unattested'})
    monkeypatch.setattr(queue, 'calculate_descriptors_batch', lambda _: ([{'id':'one'}],[],{}))
    result = queue.run_descriptor_job(DescriptorJobRequest(molecules=[{'id':'one','smiles':'CCO'}],execution_mode='NATIVE'))
    assert result.status == JobStatus.FAILED
    assert result.results is None
    assert 'attest' in result.failure_reason.lower()


def test_partial_rdkit_batch_cannot_be_completed(monkeypatch):
    from aidd_worker.models import FailureRecord
    monkeypatch.setattr(queue, 'capture_full_environment', lambda: {'environment_sha256':'test'})
    monkeypatch.setattr(queue, 'detect_rdkit', lambda: {'installed':False,'version':None})
    monkeypatch.setattr(queue, 'calculate_descriptors_batch', lambda _: ([{'id':'one'}],
        [FailureRecord(molecule_id='two',error_type='invalid',error_message='bad molecule')],{}))
    result = queue.run_descriptor_job(DescriptorJobRequest(molecules=[{'id':'one','smiles':'CCO'}, {'id':'two','smiles':'bad'}],execution_mode='DEMO_FALLBACK'))
    assert result.status == JobStatus.FAILED
    assert result.failed_count == 1
    assert 'PARTIAL' in result.failure_reason


def test_seed_zero_is_preserved_in_demo_provenance(monkeypatch):
    from aidd_worker.services import vina_service
    from aidd_worker.models import DockingJobRequest, SearchBoxConfig
    monkeypatch.setattr(vina_service, 'detect_vina', lambda: {'installed':False,'version':None,'path':None})
    request = DockingJobRequest(receptor_pdbqt=vina_service.EGFR_4WKQ_RECEPTOR_PDBQT,
        ligands=[{'id':'one','smiles':'CCO'}],seed=0,execution_mode='DEMO_FALLBACK',
        search_box=SearchBoxConfig(center_x=0,center_y=0,center_z=0))
    _, _, _, meta = vina_service.execute_docking_job('job_zero_seed',request)
    assert meta['seed'] == 0
