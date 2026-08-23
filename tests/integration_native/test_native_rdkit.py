"""
AIDD Lab OS - Native RDKit Integration Test (Tier 3: NATIVE INTEGRATION)
Executes directly through native RDKit C++ binaries. Skips cleanly if RDKit is not installed on host.
"""

import sys
import pytest

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from aidd_worker.services.capability_service import detect_rdkit
from aidd_worker.services.rdkit_service import calculate_descriptors_batch, MoleculeInput

def test_native_rdkit_calculation():
    rdk_info = detect_rdkit()
    if not rdk_info["installed"]:
        pytest.skip("SKIPPED — NATIVE DEPENDENCY UNAVAILABLE (RDKit not installed in host environment)")

    # Execute through real native RDKit
    molecules = [
        MoleculeInput(id="RDK-1", name="Aspirin", smiles="CC(=O)Oc1ccccc1C(=O)O"),
        MoleculeInput(id="RDK-2", name="Caffeine", smiles="CN1C=NC2=C1C(=O)N(C(=O)N2C)C")
    ]
    successful, failures, meta = calculate_descriptors_batch(molecules)
    assert len(successful) == 2
    assert meta["production_ready"] is True
    assert "RDKit" in meta["engine"]
