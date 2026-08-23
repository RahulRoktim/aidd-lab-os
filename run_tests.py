"""
AIDD Lab OS - Unified Multi-Tier Test Runner
Executes: UNIT, FIXTURE, NATIVE INTEGRATION, SCIENTIFIC AUDIT, and E2E suites.
"""

import sys
import os
import traceback

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

def run_all_tiers():
    print("=" * 80)
    print("AIDD LAB OS — UNIFIED MULTI-TIER TEST SUITE (v1.4.0)")
    print("=" * 80)

    results = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0}

    # 1. TIER 1: UNIT TESTS
    print("\n>>> TIER 1: UNIT TESTS")
    try:
        from tests.test_unit import test_search_box_positive_bounds, test_pdbqt_format_validation, test_sha256_checksum
        test_search_box_positive_bounds()
        print("  ✓ test_search_box_positive_bounds PASSED")
        test_pdbqt_format_validation()
        print("  ✓ test_pdbqt_format_validation PASSED")
        test_sha256_checksum()
        print("  ✓ test_sha256_checksum PASSED")
        results["PASSED"] += 3
    except Exception as e:
        print(f"  ✕ UNIT TESTS FAILED: {e}")
        traceback.print_exc()
        results["FAILED"] += 1

    # 2. TIER 2: FIXTURE TESTS
    print("\n>>> TIER 2: FIXTURE TESTS")
    try:
        from tests.test_fixture import test_vina_standard_log_fixture_parsing, test_vina_empty_log_parsing
        test_vina_standard_log_fixture_parsing()
        print("  ✓ test_vina_standard_log_fixture_parsing PASSED")
        test_vina_empty_log_parsing()
        print("  ✓ test_vina_empty_log_parsing PASSED")
        results["PASSED"] += 2
    except Exception as e:
        print(f"  ✕ FIXTURE TESTS FAILED: {e}")
        traceback.print_exc()
        results["FAILED"] += 1

    # 3. TIER 3: NATIVE INTEGRATION TESTS
    print("\n>>> TIER 3: NATIVE INTEGRATION TESTS (REAL SCIENTIFIC BINARIES)")
    from aidd_worker.services.capability_service import detect_rdkit, detect_vina

    rdk = detect_rdkit()
    if rdk["installed"]:
        try:
            from tests.integration_native.test_native_rdkit import test_native_rdkit_calculation
            test_native_rdkit_calculation()
            print("  ✓ test_native_rdkit_calculation PASSED (Native C++ RDKit)")
            results["PASSED"] += 1
        except Exception as e:
            print(f"  ✕ NATIVE RDKIT FAILED: {e}")
            results["FAILED"] += 1
    else:
        print("  - test_native_rdkit_calculation: SKIPPED — NATIVE DEPENDENCY UNAVAILABLE (RDKit not installed)")
        results["SKIPPED"] += 1

    vina = detect_vina()
    if vina["installed"]:
        try:
            from tests.integration_native.test_native_vina import test_native_vina_docking_subprocess
            test_native_vina_docking_subprocess()
            print("  ✓ test_native_vina_docking_subprocess PASSED (Native AutoDock Vina Subprocess)")
            results["PASSED"] += 1
        except Exception as e:
            print(f"  ✕ NATIVE VINA FAILED: {e}")
            results["FAILED"] += 1
    else:
        print("  - test_native_vina_docking_subprocess: SKIPPED — NATIVE DEPENDENCY UNAVAILABLE (AutoDock Vina binary not in PATH)")
        results["SKIPPED"] += 1

    # 4. TIER 4: WORKER QUEUE & RUNTIME
    print("\n>>> TIER 4: WORKER QUEUE & RUNTIME AUDIT")
    try:
        from tests.test_worker import run_worker_tests
        run_worker_tests()
        results["PASSED"] += 8
    except Exception as e:
        print(f"  ✕ WORKER SUITE FAILED: {e}")
        traceback.print_exc()
        results["FAILED"] += 1

    # 5. TIER 5: SCIENTIFIC AUDIT & PROVENANCE
    print("\n>>> TIER 5: SCIENTIFIC AUDIT & PROVENANCE REGRESSION")
    try:
        from tests.test_scientific_audit import run_scientific_audit
        run_scientific_audit()
        results["PASSED"] += 14
    except Exception as e:
        print(f"  ✕ SCIENTIFIC AUDIT FAILED: {e}")
        traceback.print_exc()
        results["FAILED"] += 1

    # 6. TIER 6: END-TO-END WORKFLOW
    print("\n>>> TIER 6: END-TO-END DISCOVERY WORKFLOW")
    try:
        from tests.test_e2e import run_tests
        run_tests()
        results["PASSED"] += 13
    except Exception as e:
        print(f"  ✕ E2E DISCOVERY FAILED: {e}")
        traceback.print_exc()
        results["FAILED"] += 1

    print("\n" + "=" * 80)
    print(f"FINAL AUDIT RESULTS: {results['PASSED']} Passed | {results['FAILED']} Failed | {results['SKIPPED']} Skipped")
    print("=" * 80)
    return results["FAILED"] == 0

if __name__ == "__main__":
    success = run_all_tiers()
    sys.exit(0 if success else 1)
