import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import validate_native_runtime
from validate_native_runtime import NativeValidationHarness, validate_provenance_dag
from app import database, services
from aidd_worker import config
from aidd_worker.models import DockingJobRequest, SearchBoxConfig
from aidd_worker.services import capability_service, vina_service


ROUND2_LOG = """AutoDock Vina 36dd023-mod
mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1         -8.7      0.000      0.000
"""


def native_request(ligand_id="LIG-FIXTURE-B"):
    return DockingJobRequest(
        receptor_pdbqt=vina_service.EGFR_4WKQ_RECEPTOR_PDBQT,
        receptor_name="Synthetic receptor fixture B",
        ligands=[{
            "id": ligand_id,
            "name": "Synthetic ligand fixture B",
            "pdbqt": vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT,
        }],
        search_box=SearchBoxConfig(
            center_x=22.4,
            center_y=0.8,
            center_z=52.5,
            size_x=20.0,
            size_y=20.0,
            size_z=20.0,
        ),
        num_modes=1,
        execution_mode="NATIVE",
    )


def verified_vina():
    return {
        "installed": True,
        "path": "/trusted/vina",
        "expected_path": "/trusted/vina",
        "version": "AutoDock Vina 36dd023-mod",
        "expected_version": "AutoDock Vina 36dd023-mod",
        "production_ready": True,
        "identity_verified": True,
        "binary_sha256": "a" * 64,
        "expected_binary_sha256": "a" * 64,
        "binary_digest_verified": True,
        "path_verified": True,
        "package_metadata_verified": True,
        "version_output_sha256": "b" * 64,
    }


def output_path_from_command(args):
    config_path = Path(args[0][2])
    return next(
        Path(line.split("=", 1)[1].strip())
        for line in config_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("out =")
    )


def test_round2_banner_and_pdbqt_fake_is_rejected_by_release_digest(monkeypatch, tmp_path):
    fake_fixture = Path(__file__).parent / "fixtures" / "fake_vina_round2.sh"
    fake = tmp_path / "vina"
    shutil.copy2(fake_fixture, fake)
    os.chmod(fake, 0o755)
    ligand = tmp_path / "ligand.pdbqt"
    output = tmp_path / "output.pdbqt"
    config_file = tmp_path / "fake-config.txt"
    ligand.write_text(vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT, encoding="utf-8")
    config_file.write_text(f"ligand = {ligand}\nout = {output}\n", encoding="utf-8")

    version = subprocess.run([str(fake), "--version"], capture_output=True, text=True, check=True)
    forged = subprocess.run([str(fake), "--config", str(config_file)], capture_output=True, text=True, check=True)
    assert version.stdout.strip() == "AutoDock Vina 36dd023-mod"
    assert "mode |   affinity" in forged.stdout
    assert output.exists() and output.stat().st_size > 0
    assert output.read_text(encoding="utf-8") != ligand.read_text(encoding="utf-8")

    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(config, "VINA_EXECUTABLE", "vina")
    detected = capability_service.detect_vina()
    assert detected["installed"] is True
    assert detected["binary_sha256"] != detected["expected_binary_sha256"]
    assert detected["binary_digest_verified"] is False
    assert detected["identity_verified"] is False
    assert detected["production_ready"] is False


def test_untrusted_round2_fake_refuses_native_computed_execution(monkeypatch, tmp_path):
    fake = Path(__file__).parent / "fixtures" / "fake_vina_round2.sh"
    os.chmod(fake, 0o755)
    monkeypatch.setattr(config, "VINA_EXECUTABLE", str(fake))
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))

    results, failures, _, meta = vina_service.execute_docking_job("job_round2_untrusted", native_request())

    assert results == []
    assert failures[0].error_type == "VinaBinaryUnavailable"
    assert meta["vina_binary_digest_verified"] is False
    assert meta["exit_code"] is None


def test_unrelated_output_pdbqt_fails_ligand_identity_integrity(monkeypatch, tmp_path):
    monkeypatch.setattr(vina_service.config, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(vina_service, "detect_vina", verified_vina)

    def write_unrelated_output(*args, **kwargs):
        output_path = output_path_from_command(args)
        unrelated = vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT.replace("0.050 C ", "0.050 OA", 1)
        output_path.write_text(f"MODEL 1\n{unrelated}\nENDMDL\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=ROUND2_LOG, stderr="")

    monkeypatch.setattr(vina_service.subprocess, "run", write_unrelated_output)
    results, failures, _, meta = vina_service.execute_docking_job("job_unrelated_output", native_request())

    assert results == []
    assert failures[0].error_type == "VinaLigandOutputIntegrityError"
    assert "does not match the submitted ligand" in failures[0].error_message
    assert meta["exit_code"] is None


@pytest.mark.parametrize("ligand_id", [
    "../../escape",
    "..\\..\\escape",
    "line\nbreak",
    "/absolute/path",
    "control\x01character",
])
def test_unsafe_ligand_ids_are_rejected_during_request_validation(ligand_id):
    with pytest.raises(ValidationError, match="ID matching"):
        native_request(ligand_id)


def test_prepared_ligand_ids_must_bind_exactly_to_dataset_ids(monkeypatch):
    monkeypatch.setattr(services, "get_project", lambda _: {"id": "proj"})
    monkeypatch.setattr(services, "get_dataset_detail", lambda _: {"molecules": [{"id": "DATASET-1"}]})
    with pytest.raises(ValueError, match="must exactly match"):
        services.import_or_run_docking(
            project_id="proj",
            input_dataset_id="ds",
            result_origin="COMPUTED",
            receptor_pdbqt=vina_service.EGFR_4WKQ_RECEPTOR_PDBQT,
            prepared_ligands=[{"id": "OTHER-1", "pdbqt": vina_service.SYNTHETIC_LIGAND_FIXTURE_B_PDBQT}],
        )


def test_rdkit_plausible_wrong_shim_fails_known_answer_proof():
    fake_modules = {
        "Chem": SimpleNamespace(MolFromSmiles=lambda smiles: object()),
        "Descriptors": SimpleNamespace(MolWt=lambda mol: 180.15, MolLogP=lambda mol: 1.30),
        "Lipinski": SimpleNamespace(NumHDonors=lambda mol: 1, NumHAcceptors=lambda mol: 3),
        "rdMolDescriptors": SimpleNamespace(CalcMolFormula=lambda mol: "C9H8O4"),
    }
    evidence = capability_service._run_rdkit_known_answers(fake_modules)
    assert evidence["passed"] is False
    caffeine = next(item for item in evidence["compounds"] if item["name"] == "caffeine")
    assert caffeine["passed"] is False


def test_validator_rdkit_proof_rejects_plausible_wrong_worker_values(monkeypatch):
    harness = NativeValidationHarness()
    harness.report["worker_readiness"] = {
        "rdkit_ready": True,
        "rdkit_module_origin_verified": True,
        "rdkit_native_components_verified": True,
        "rdkit_package_metadata_verified": True,
        "rdkit_known_answer_verified": True,
        "rdkit_module_path": "/trusted/rdkit/__init__.py",
    }
    wrong_results = [
        {"id": "ASPIRIN-PROOF", "formula": "C9H8O4", "molecular_weight": 180.16, "hbd": 1, "hba": 3, "logp": 1.31, "engine": "RDKit v2023.09.5", "production_ready": True, "result_origin": "COMPUTED"},
        {"id": "CAFFEINE-PROOF", "formula": "C8H10N4O2", "molecular_weight": 194.19, "hbd": 0, "hba": 5, "logp": -1.03, "engine": "RDKit v2023.09.5", "production_ready": True, "result_origin": "COMPUTED"},
    ]
    monkeypatch.setattr(validate_native_runtime, "http_post", lambda *args, **kwargs: (True, {
        "job_id": "shim-job",
        "status": "COMPLETED",
        "successful_count": 2,
        "failed_count": 0,
        "failures": [],
        "results": wrong_results,
    }))
    assert harness.run_native_rdkit_proof() is False
    assert harness.report["rdkit_proof"]["known_answer_verified"] is False


def test_provenance_validation_rejects_dangling_edges_and_cycles():
    dangling = validate_provenance_dag(
        {"nodes": [{"id": "ds1"}, {"id": "exp1"}], "edges": [{"source": "missing", "target": "exp1"}]},
        [("ds1", "exp1")],
    )
    assert dangling["valid"] is False
    assert dangling["dangling_edges"]
    assert dangling["missing_expected_edges"]

    cyclic = validate_provenance_dag(
        {
            "nodes": [{"id": "ds1"}, {"id": "exp1"}],
            "edges": [{"source": "ds1", "target": "exp1"}, {"source": "exp1", "target": "ds1"}],
        },
        [("ds1", "exp1")],
    )
    assert cyclic["valid"] is False
    assert cyclic["cycle_detected"] is True


def test_locked_experiment_scientific_fields_are_database_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "locked.db"))
    database.init_db(force_recreate=True)
    project = services.create_project("Lock enforcement")
    imported = services.import_molecules_from_csv_or_list(
        project["id"],
        [{"id": "LOCK-1", "name": "Ethanol", "smiles": "CCO"}],
    )
    experiment_id = imported["experiment_id"]

    with pytest.raises(sqlite3.IntegrityError, match="scientific fields are immutable"):
        with database.get_db() as connection:
            connection.execute("UPDATE experiments SET metrics = ? WHERE id = ?", ('{"tampered": true}', experiment_id))

    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        with database.get_db() as connection:
            connection.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))

    note = services.append_experiment_note(experiment_id, "Append-only observation", "Tester")
    assert note["status"] == "appended"
    assert len(note["notes_log"]) == 1


def test_database_record_survives_non_destructive_reinitialization(monkeypatch, tmp_path):
    db_path = tmp_path / "persistent.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db(force_recreate=True)
    project = services.create_project("Persistent marker")
    database.init_db(force_recreate=False)
    assert services.get_project(project["id"])["name"] == "Persistent marker"
