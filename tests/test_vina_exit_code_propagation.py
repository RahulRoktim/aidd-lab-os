import json
from types import SimpleNamespace

import pytest

from aidd_worker.models import DockingJobRequest, SearchBoxConfig
from aidd_worker.services import job_queue_service, job_service, vina_service


def _request(ligand_count=1):
    ligands = [
        {
            "id": f"LIG-{index + 1}",
            "name": f"Ligand {index + 1}",
            "pdbqt": vina_service.ERLOTINIB_LIGAND_PDBQT,
        }
        for index in range(ligand_count)
    ]
    return DockingJobRequest(
        receptor_pdbqt=vina_service.EGFR_4WKQ_RECEPTOR_PDBQT,
        ligands=ligands,
        search_box=SearchBoxConfig(
            center_x=22.4,
            center_y=0.8,
            center_z=52.5,
            size_x=20.0,
            size_y=20.0,
            size_z=20.0,
        ),
        execution_mode="NATIVE",
    )


def test_successful_native_vina_execution_returns_zero_exit_code(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        vina_service,
        "detect_vina",
        lambda: {"installed": True, "path": "/usr/bin/vina", "version": "AutoDock Vina test"},
    )
    monkeypatch.setattr(
        vina_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=vina_service.VINA_STANDARD_LOG_FIXTURE,
            stderr="",
        ),
    )

    results, failures, _, meta = vina_service.execute_docking_job("job_success", _request())

    assert len(results) == 1
    assert failures == []
    assert meta["exit_code"] == 0


def test_native_vina_preserves_nonzero_code_across_multiple_ligands(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        vina_service,
        "detect_vina",
        lambda: {"installed": True, "path": "/usr/bin/vina", "version": "AutoDock Vina test"},
    )
    process_results = iter(
        [
            SimpleNamespace(returncode=7, stdout="", stderr="native failure"),
            SimpleNamespace(returncode=0, stdout=vina_service.VINA_STANDARD_LOG_FIXTURE, stderr=""),
        ]
    )
    monkeypatch.setattr(vina_service.subprocess, "run", lambda *args, **kwargs: next(process_results))

    results, failures, _, meta = vina_service.execute_docking_job("job_partial", _request(2))

    assert len(results) == 1
    assert len(failures) == 1
    assert meta["exit_code"] == 7


def test_zero_is_not_fabricated_when_native_output_is_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        vina_service,
        "detect_vina",
        lambda: {"installed": True, "path": "/usr/bin/vina", "version": "AutoDock Vina test"},
    )
    process_results = iter(
        [
            SimpleNamespace(returncode=0, stdout="unparseable output", stderr=""),
            SimpleNamespace(returncode=0, stdout=vina_service.VINA_STANDARD_LOG_FIXTURE, stderr=""),
        ]
    )
    monkeypatch.setattr(vina_service.subprocess, "run", lambda *args, **kwargs: next(process_results))

    results, failures, _, meta = vina_service.execute_docking_job("job_incomplete", _request(2))

    assert len(results) == 1
    assert len(failures) == 1
    assert meta["exit_code"] is None


@pytest.mark.parametrize("service", [job_service, job_queue_service])
def test_job_managers_propagate_docking_exit_code(monkeypatch, tmp_path, service):
    monkeypatch.setattr(service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        service,
        "detect_vina",
        lambda: {"installed": True, "path": "/usr/bin/vina", "version": "AutoDock Vina test"},
    )
    if service is job_queue_service:
        monkeypatch.setattr(
            service,
            "capture_full_environment",
            lambda: {"environment_sha256": "test-environment"},
        )
    monkeypatch.setattr(
        service,
        "execute_docking_job",
        lambda job_id, request: (
            [
                {
                    "molecule_id": "LIG-1",
                    "best_affinity_kcal_mol": -7.5,
                    "result_origin": "COMPUTED",
                }
            ],
            [],
            [],
            {"stdout": "native stdout", "stderr": "", "exit_code": 0},
        ),
    )

    job = service.run_docking_job(_request())

    assert job.exit_code == 0
    manifest_path = tmp_path / job.job_id / "job_manifest.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["exit_code"] == 0
