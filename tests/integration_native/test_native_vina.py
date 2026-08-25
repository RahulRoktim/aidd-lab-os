"""
AIDD Lab OS - Native AutoDock Vina Integration Test (Tier 3: NATIVE INTEGRATION)
Executes real AutoDock Vina subprocess with receptor and ligand PDBQT files.
Skips cleanly if AutoDock Vina binary is not installed on host.
"""

import sys
import pytest

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from aidd_worker.services.capability_service import detect_vina
from aidd_worker.models import DockingJobRequest, SearchBoxConfig
from aidd_worker.services.vina_service import (
    execute_docking_job,
    EGFR_4WKQ_RECEPTOR_PDBQT, ERLOTINIB_LIGAND_PDBQT
)

def test_native_vina_docking_subprocess():
    vina_info = detect_vina()
    if not vina_info["installed"]:
        pytest.skip("SKIPPED — NATIVE DEPENDENCY UNAVAILABLE (AutoDock Vina binary not found in PATH)")

    req = DockingJobRequest(
        receptor_pdbqt=EGFR_4WKQ_RECEPTOR_PDBQT,
        receptor_name="EGFR Kinase Domain (4WKQ)",
        ligands=[{"id": "LIG-ERL", "name": "Erlotinib Fragment", "pdbqt": ERLOTINIB_LIGAND_PDBQT}],
        search_box=SearchBoxConfig(center_x=22.4, center_y=0.8, center_z=52.5, size_x=20.0, size_y=20.0, size_z=20.0),
        exhaustiveness=4, # Fast test mode
        num_modes=3,
        seed=42,
        execution_mode="NATIVE"
    )

    results, failures, artifacts, meta = execute_docking_job("test_native_vina_job", req)
    assert len(results) == 1
    assert results[0]["result_origin"] == "COMPUTED"
    assert results[0]["docking_score"] < 0.0
    assert failures == []
    assert meta["exit_code"] == 0
    assert meta["vina_identity_verified"] is True
    assert meta["vina_binary_sha256"]
    assert results[0]["output_pdbqt_hash"]
    assert results[0]["tool_version"] == vina_info["version"]
