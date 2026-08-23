from validate_native_runtime import NativeValidationHarness

def test_validator_false_positive():
    harness = NativeValidationHarness()
    # Mock states
    harness.report = {
        "host": {"system": "Mock", "release": "Mock", "architecture": "Mock", "python_version": "Mock", "cpu_count": 4},
        "generated_at": "2026-08-23T14:00:00Z",
        "validation_mode": "AUTO",
        "preflight_checks": {"data_dir_writable": True},
        "worker_readiness": {"health": "OK", "rdkit_ready": True, "vina_ready": True},
        "rdkit_proof": {"is_native_rdkit": True, "status": "COMPLETED"},
        "rdkit_integration_suite": {"validation_passed": True, "successful_count": 55, "failed_count": 0},
        "vina_proof": {"is_native_vina_executed": True, "status": "COMPLETED", "successful_count": 1, "failed_count": 0, "exit_code": 1},
        "e2e_application_workflow": {"success": True, "provenance_edges": 1, "reproduction_match": True}
    }

    harness.compile_report(json_path="test_mock.json", html_path="test_mock.html")
    assert harness.report["overall_status"] == "PARTIALLY_VERIFIED"
