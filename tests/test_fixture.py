"""
AIDD Lab OS - Fixture Test Suite (Tier 2: FIXTURE)
Pure Python / standard library compatible tests for parsing standard multi-pose AutoDock Vina log outputs and PDBQT records.
"""

import sys
import os

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from aidd_worker.services.vina_service import parse_vina_log_output, VINA_STANDARD_LOG_FIXTURE

def test_vina_standard_log_fixture_parsing():
    poses = parse_vina_log_output(VINA_STANDARD_LOG_FIXTURE)
    assert len(poses) == 9, "Standard fixture must parse exactly 9 binding poses"
    
    # Top pose assertions
    top = poses[0]
    assert top["rank"] == 1
    assert top["affinity_kcal_mol"] == -10.4
    assert top["rmsd_lower_bound"] == 0.0
    assert top["rmsd_upper_bound"] == 0.0

    # Intermediate poses assertions
    p2 = poses[1]
    assert p2["rank"] == 2
    assert p2["affinity_kcal_mol"] == -9.8
    assert p2["rmsd_lower_bound"] == 1.423
    assert p2["rmsd_upper_bound"] == 2.105

    # Lowest ranked pose
    p9 = poses[-1]
    assert p9["rank"] == 9
    assert p9["affinity_kcal_mol"] == -7.4
    assert p9["rmsd_lower_bound"] == 5.120

def test_vina_empty_log_parsing():
    poses = parse_vina_log_output("Some non-table output from crashed process")
    assert len(poses) == 0

if __name__ == "__main__":
    test_vina_standard_log_fixture_parsing()
    test_vina_empty_log_parsing()
    print("All Fixture Tests Passed!")
