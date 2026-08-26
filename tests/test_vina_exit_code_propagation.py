import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from aidd_worker.models import DockingJobRequest, SearchBoxConfig
from aidd_worker.services import job_queue_service, job_service, vina_service


VERIFIED_VINA = {
    "installed": True,
    "path": "/usr/bin/vina",
    "version": "AutoDock Vina test",
    "production_ready": True,
    "identity_verified": True,
    "binary_sha256": "a" * 64,
    "expected_binary_sha256": "a" * 64,
    "binary_digest_verified": True,
    "path_verified": True,
    "package_metadata_verified": True,
    "expected_path": "/usr/bin/vina",
    "version_output_sha256": "b" * 64,
}


def _completed_process(args, stdout=vina_service.VINA_STANDARD_LOG_FIXTURE, returncode=0, write_output=True):
    if write_output and returncode == 0:
        config_path = Path(args[0][2])
        out_path = next(
            Path(line.split("=", 1)[1].strip())
            for line in config_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("out =")
        )
        pose_count = max(1, len(vina_service.parse_vina_log_output(stdout)))
        output = "\n".join(
            f"MODEL {index}\n{vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT}\nENDMDL"
            for index in range(1, pose_count + 1)
        )
        out_path.write_text(output, encoding="utf-8")
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="" if returncode == 0 else "native failure")


def _request(ligand_count=1):
    ligands = [
        {
            "id": f"LIG-{index + 1}",
            "name": f"Ligand {index + 1}",
            "pdbqt": vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT,
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
        lambda: VERIFIED_VINA,
    )
    monkeypatch.setattr(
        vina_service.subprocess,
        "run",
        lambda *args, **kwargs: _completed_process(args),
    )

    results, failures, _, meta = vina_service.execute_docking_job("job_success", _request())

    assert len(results) == 1
    assert failures == []
    assert meta["exit_code"] == 0


def test_native_reproducibility_hash_excludes_job_specific_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(vina_service, "detect_vina", lambda: VERIFIED_VINA)
    monkeypatch.setattr(vina_service.subprocess, "run", lambda *args, **kwargs: _completed_process(args))

    first_results, first_failures, _, first_meta = vina_service.execute_docking_job("job_first", _request())
    second_results, second_failures, _, second_meta = vina_service.execute_docking_job("job_second", _request())

    assert first_failures == second_failures == []
    assert first_results[0]["config_sha256"] != second_results[0]["config_sha256"]
    assert first_meta["reproducibility_hash"] == second_meta["reproducibility_hash"]


def test_native_vina_preserves_nonzero_code_across_multiple_ligands(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        vina_service,
        "detect_vina",
        lambda: VERIFIED_VINA,
    )
    call_count = 0
    def run_process(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _completed_process(args, returncode=7) if call_count == 1 else _completed_process(args)
    monkeypatch.setattr(vina_service.subprocess, "run", run_process)

    results, failures, _, meta = vina_service.execute_docking_job("job_partial", _request(2))

    assert len(results) == 1
    assert len(failures) == 1
    assert meta["exit_code"] == 7


def test_zero_is_not_fabricated_when_native_output_is_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(
        vina_service,
        "detect_vina",
        lambda: VERIFIED_VINA,
    )
    call_count = 0
    def run_process(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _completed_process(args, stdout="unparseable output") if call_count == 1 else _completed_process(args)
    monkeypatch.setattr(vina_service.subprocess, "run", run_process)

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
        lambda: VERIFIED_VINA,
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
                    "docking_score": -7.5,
                    "best_affinity_kcal_mol": -7.5,
                    "result_origin": "COMPUTED",
                    "vina_binary_digest_verified": True,
                    "vina_path_verified": True,
                    "vina_package_metadata_verified": True,
                    "output_created_after_start": True,
                    "output_path_verified": True,
                    "ligand_output_integrity": {"verified": True},
                }
            ],
            [],
            [],
            {
                "stdout": "native stdout", "stderr": "", "exit_code": 0,
                "tool": "AutoDock Vina", "tool_version": "AutoDock Vina test",
                "production_ready": True, "vina_identity_verified": True,
                "vina_binary_sha256": "a" * 64,
                "vina_expected_binary_sha256": "a" * 64,
                "vina_binary_digest_verified": True,
                "vina_path_verified": True,
                "vina_package_metadata_verified": True,
            },
        ),
    )

    job = service.run_docking_job(_request())

    assert job.exit_code == 0
    manifest_path = tmp_path / job.job_id / "job_manifest.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["exit_code"] == 0
