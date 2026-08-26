import validate_native_runtime
from validate_native_runtime import NativeValidationHarness

def test_validator_false_positive(tmp_path):
    harness = NativeValidationHarness()
    # Mock states
    harness.report = {
        "host": {"system": "Mock", "release": "Mock", "architecture": "Mock", "python_version": "Mock", "cpu_count": 4},
        "generated_at": "2026-08-23T14:00:00Z",
        "validation_mode": "AUTO",
        "preflight_checks": {"storage_writable": True},
        "worker_readiness": {
            "health": "OK", "rdkit_ready": True, "vina_ready": True,
            "rdkit_module_origin_verified": True, "rdkit_native_components_verified": True,
            "rdkit_package_metadata_verified": True, "rdkit_known_answer_verified": True,
            "vina_identity_verified": True, "vina_version": "AutoDock Vina test",
            "vina_binary_sha256": "a" * 64, "vina_version_output_sha256": "b" * 64,
            "vina_expected_binary_sha256": "a" * 64, "vina_binary_digest_verified": True,
            "vina_path_verified": True, "vina_package_metadata_verified": True,
        },
        "rdkit_proof": {"is_native_rdkit": True, "known_answer_verified": True, "status": "COMPLETED"},
        "rdkit_integration_suite": {
            "validation_passed": True, "production_ready": True,
            "successful_count": 55, "failed_count": 0,
            "sample_results": [{"result_origin": "COMPUTED"}],
            "rdkit_attestation": {"known_answer_verified": True, "native_components_verified": True, "package_metadata_verified": True},
        },
        "vina_proof": {"is_native_vina_executed": True, "status": "COMPLETED", "successful_count": 1, "failed_count": 0, "exit_code": 1},
        "e2e_application_workflow": {
            "success": True,
            "provenance_edges": 1,
            "provenance_validation": {"valid": True},
            "manifest_exported": True,
            "reproduction_match": True
        }
    }

    harness.compile_report(
        json_path=str(tmp_path / "test_mock.json"),
        html_path=str(tmp_path / "test_mock.html")
    )
    assert harness.report["overall_status"] == "PARTIALLY_VERIFIED"
    assert harness.report["mandatory_checks"]["vina_proof"] is False
    vina_summary = next(
        row for row in harness.report["summary_table"]
        if row["item"] == "Native AutoDock Vina Execution"
    )
    assert vina_summary["status"] == "FAIL"


def test_vina_proof_records_worker_exit_code(monkeypatch):
    harness = NativeValidationHarness()
    harness.report["worker_readiness"] = {
        "vina_ready": True,
        "vina_identity_verified": True,
        "vina_binary_sha256": "a" * 64,
        "vina_expected_binary_sha256": "a" * 64,
        "vina_binary_digest_verified": True,
        "vina_path_verified": True,
        "vina_package_metadata_verified": True,
    }
    worker_result = {
        "job_id": "job_native_vina",
        "status": "COMPLETED",
        "tool": "AutoDock Vina",
        "tool_version": "AutoDock Vina test",
        "worker_id": "worker_test",
        "production_ready": True,
        "execution_mode": "NATIVE",
        "successful_count": 1,
        "failed_count": 0,
        "failures": [],
        "exit_code": 0,
        "results": [{
            "molecule_id": "LIG-FIXTURE-B",
            "docking_score": -7.5,
            "best_affinity_kcal_mol": -7.5,
            "poses": [{"rank": 1}],
            "result_origin": "COMPUTED",
            "tool": "AutoDock Vina",
            "tool_version": "AutoDock Vina test",
            "vina_binary_sha256": "a" * 64,
            "vina_expected_binary_sha256": "a" * 64,
            "vina_binary_digest_verified": True,
            "vina_path_verified": True,
            "vina_package_metadata_verified": True,
            "output_pdbqt_hash": "c" * 64,
            "receptor_hash": "d" * 64,
            "ligand_hash": "e" * 64,
            "output_created_after_start": True,
            "output_path_verified": True,
            "ligand_output_integrity": {"verified": True},
            "prepared_ligand_id": "LIG-FIXTURE-B",
        }],
        "artifacts": [{"file_type": "pdbqt_output", "size_bytes": 123, "sha256_hash": "c" * 64}],
        "metrics": {
            "vina_identity_verified": True,
            "vina_binary_sha256": "a" * 64,
            "vina_expected_binary_sha256": "a" * 64,
            "vina_binary_digest_verified": True,
            "vina_path_verified": True,
            "vina_package_metadata_verified": True,
            "vina_version_output_sha256": "b" * 64,
            "stdout_sha256": "f" * 64,
            "output_pdbqt_hashes": ["c" * 64],
        },
        "stdout": "native stdout",
        "stderr": "",
        "reproducibility_hash": "hash"
    }
    monkeypatch.setattr(validate_native_runtime, "http_post", lambda *args, **kwargs: (True, worker_result))

    assert harness.run_native_vina_proof() is True
    assert harness.report["vina_proof"]["exit_code"] == 0
