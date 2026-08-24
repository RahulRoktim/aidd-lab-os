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
        "worker_readiness": {"health": "OK", "rdkit_ready": True, "vina_ready": True},
        "rdkit_proof": {"is_native_rdkit": True, "status": "COMPLETED"},
        "rdkit_integration_suite": {"validation_passed": True, "successful_count": 55, "failed_count": 0},
        "vina_proof": {"is_native_vina_executed": True, "status": "COMPLETED", "successful_count": 1, "failed_count": 0, "exit_code": 1},
        "e2e_application_workflow": {
            "success": True,
            "provenance_edges": 1,
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
    harness.report["worker_readiness"] = {"vina_ready": True}
    worker_result = {
        "job_id": "job_native_vina",
        "status": "COMPLETED",
        "tool": "AutoDock Vina test",
        "production_ready": True,
        "successful_count": 1,
        "failed_count": 0,
        "failures": [],
        "exit_code": 0,
        "results": [{
            "docking_score": -7.5,
            "best_affinity_kcal_mol": -7.5,
            "poses": [{"rank": 1}],
            "result_origin": "COMPUTED"
        }],
        "artifacts": [],
        "stdout": "native stdout",
        "stderr": "",
        "reproducibility_hash": "hash"
    }
    monkeypatch.setattr(validate_native_runtime, "http_post", lambda *args, **kwargs: (True, worker_result))

    assert harness.run_native_vina_proof() is True
    assert harness.report["vina_proof"]["exit_code"] == 0
