import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import database, services
from aidd_worker import config
from aidd_worker.models import DockingJobRequest, MoleculeInput, SearchBoxConfig
from aidd_worker.services import capability_service, rdkit_service, vina_service
from validate_native_runtime import NativeValidationHarness


def _native_request():
    return DockingJobRequest(
        receptor_pdbqt=vina_service.EGFR_4WKQ_RECEPTOR_PDBQT,
        ligands=[{
            "id": "LIG-1",
            "name": "Synthetic ligand fixture",
            "pdbqt": vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT,
        }],
        search_box=SearchBoxConfig(
            center_x=22.4, center_y=0.8, center_z=52.5,
            size_x=20.0, size_y=20.0, size_z=20.0,
        ),
        execution_mode="NATIVE",
    )


def _verified_vina():
    return {
        "installed": True,
        "path": "/usr/bin/vina",
        "version": "AutoDock Vina v1.2.5",
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


def test_fake_named_vina_printing_table_and_zero_exit_is_rejected(monkeypatch):
    fake_path = Path(__file__).parent / "fixtures" / "fake_vina.sh"
    os.chmod(fake_path, 0o755)
    monkeypatch.setattr(config, "VINA_EXECUTABLE", str(fake_path))

    detected = capability_service.detect_vina()

    assert detected["installed"] is True
    assert detected["identity_verified"] is False
    assert detected["production_ready"] is False
    assert detected["binary_digest_verified"] is False
    assert detected["version_probe_exit_code"] is None
    assert detected["version"] is None


def test_valid_vina_identity_preserves_exact_version_and_binary_hash(monkeypatch, tmp_path):
    binary = tmp_path / "vina"
    binary.write_bytes(b"real-binary-test-bytes")
    digest = capability_service.hashlib.sha256(binary.read_bytes()).hexdigest()
    monkeypatch.setattr(config, "VINA_EXECUTABLE", str(binary))
    monkeypatch.setattr(config, "RELEASE_ATTESTATION", {
        **config.RELEASE_ATTESTATION,
        "vina": {
            **config.RELEASE_ATTESTATION["vina"],
            "expected_path": str(binary),
            "expected_binary_sha256": digest,
            "expected_version": "AutoDock Vina v9.8.7-custom+build42",
        },
    })
    monkeypatch.setattr(capability_service.shutil, "which", lambda _: str(binary))
    monkeypatch.setattr(capability_service, "_verify_conda_package", lambda _: {"verified": True, "record_path": "test", "actual": {}})
    monkeypatch.setattr(
        capability_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="AutoDock Vina v9.8.7-custom+build42\n",
            stderr="",
        ),
    )

    detected = capability_service.detect_vina()

    assert detected["installed"] is True
    assert detected["identity_verified"] is True
    assert detected["version"] == "AutoDock Vina v9.8.7-custom+build42"
    assert detected["binary_sha256"] == digest
    assert detected["binary_sha256"] == detected["expected_binary_sha256"]


def test_zero_exit_without_output_pdbqt_is_not_native_success(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(vina_service, "detect_vina", _verified_vina)
    monkeypatch.setattr(
        vina_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=vina_service.VINA_STANDARD_LOG_FIXTURE,
            stderr="",
        ),
    )

    results, failures, _, meta = vina_service.execute_docking_job("missing_output", _native_request())

    assert results == []
    assert failures[0].error_type == "VinaOutputFileMissing"
    assert meta["exit_code"] is None


def test_origin_misuse_is_rejected_before_persistence(monkeypatch):
    monkeypatch.setattr(services, "get_project", lambda _: {"id": "proj"})
    monkeypatch.setattr(services, "get_dataset_detail", lambda _: {"molecules": [{"id": "M1"}]})

    with pytest.raises(ValueError, match="requires custom_scores_csv"):
        services.import_or_run_docking("proj", "ds", result_origin="IMPORTED")
    with pytest.raises(ValueError, match="cannot be labeled COMPUTED"):
        services.import_or_run_admet("proj", "ds", result_origin="COMPUTED")


def test_rdkit_fallback_results_are_simulated_not_computed(monkeypatch):
    monkeypatch.setattr(
        rdkit_service,
        "detect_rdkit",
        lambda: {"installed": False, "version": None, "production_ready": False},
    )
    results, failures, meta = rdkit_service.calculate_descriptors_batch([
        MoleculeInput(id="M1", name="Ethanol", smiles="CCO")
    ])

    assert failures == []
    assert meta["production_ready"] is False
    assert results[0]["result_origin"] == "SIMULATED"


def test_reproduction_detects_per_molecule_score_divergence(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "reproduction.db"))
    database.init_db(force_recreate=True)
    project = services.create_project("Reproduction truth test")
    imported = services.import_molecules_from_csv_or_list(
        project["id"],
        [{"id": "M1", "name": "Ethanol", "smiles": "CCO"}],
    )
    original = services.import_or_run_docking(
        project_id=project["id"],
        input_dataset_id=imported["dataset_id"],
        result_origin="IMPORTED",
        custom_scores_csv="molecule_id,docking_score\nM1,-7.0\n",
    )

    real_import = services.import_or_run_docking

    def altered_import(**kwargs):
        kwargs["custom_scores_csv"] = "molecule_id,docking_score\nM1,-6.5\n"
        return real_import(**kwargs)

    monkeypatch.setattr(services, "import_or_run_docking", altered_import)
    reproduced = services.reproduce_experiment(original["experiment_id"])

    assert reproduced["reproduction_match"] is False
    assert any("Docking score mismatch for M1" in reason for reason in reproduced["diff_reasons"])
    assert any("reproducibility_hash mismatch" in reason for reason in reproduced["diff_reasons"])


def test_validator_html_has_no_fabricated_success_defaults(tmp_path):
    harness = NativeValidationHarness()
    harness.report["overall_status"] = "VALIDATION_FAILED"
    harness.report["mandatory_checks"] = {key: False for key in (
        "worker_rdkit", "rdkit_proof", "rdkit_suite", "worker_vina",
        "vina_proof", "provenance", "reproduction",
    )}
    harness.report["summary_table"] = [{"item": "Native AutoDock Vina Execution", "status": "FAIL"}]

    rendered = harness.render_html_report()

    assert "C9H8O4" not in rendered
    assert "180.16" not in rendered
    assert "100% Metric Equality" not in rendered
    assert "Ground-Truth" not in rendered
    assert "MISSING" in rendered


def test_clean_demo_seed_has_no_foreign_key_violations_or_false_origins(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "clean-start.db"))
    database.init_db(force_recreate=True)

    seeded = services.seed_demo_project()

    assert seeded["status"] == "seeded"
    with database.get_db() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        docking_origins = {row[0] for row in connection.execute("SELECT DISTINCT result_origin FROM docking_results")}
        admet_origins = {row[0] for row in connection.execute("SELECT DISTINCT result_origin FROM admet_results")}
        candidate_origins = {row[0] for row in connection.execute("SELECT DISTINCT result_origin FROM candidate_scores")}
    assert docking_origins == {"DEMO"}
    assert admet_origins == {"DEMO"}
    assert candidate_origins == {"DEMO"}


def test_validator_process_exits_nonzero_when_runtime_is_not_verified(tmp_path):
    report_json = tmp_path / "failed.json"
    report_html = tmp_path / "failed.html"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "validate_native_runtime.py"),
            "--mode", "LOCAL",
            "--worker-url", "http://127.0.0.1:9",
            "--app-url", "http://127.0.0.1:9",
            "--output-json", str(report_json),
            "--output-html", str(report_html),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode != 0
    assert json.loads(report_json.read_text(encoding="utf-8"))["overall_status"] != "NATIVE_RUNTIME_VERIFIED"
