"""
AIDD Lab OS - Unit Test Suite (Tier 1: UNIT)
Pure Python / standard library compatible tests for models, bounding box constraints, and checksum calculators.
"""

import sys
import os

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from aidd_worker.models import (
    SearchBoxConfig, MoleculeInput, DescriptorJobRequest,
    JobStatus, ExecutionMode, StandardizationProfile
)
from aidd_worker.services.artifact_service import compute_sha256
from aidd_worker.services.vina_service import validate_pdbqt_format, EGFR_4WKQ_RECEPTOR_PDBQT, ERLOTINIB_LIGAND_PDBQT

def test_search_box_positive_bounds():
    # Valid bounding box
    sb = SearchBoxConfig(center_x=22.4, center_y=0.8, center_z=52.5, size_x=20.0, size_y=20.0, size_z=20.0)
    assert sb.center_x == 22.4
    assert sb.size_x == 20.0

    # Negative / zero sizes must raise validation error
    caught = False
    try:
        SearchBoxConfig(center_x=0.0, center_y=0.0, center_z=0.0, size_x=-5.0, size_y=20.0, size_z=20.0)
    except ValueError:
        caught = True
    assert caught, "Negative search box size must raise error"

    caught_zero = False
    try:
        SearchBoxConfig(center_x=0.0, center_y=0.0, center_z=0.0, size_x=20.0, size_y=0.0, size_z=20.0)
    except ValueError:
        caught_zero = True
    assert caught_zero, "Zero search box size must raise error"

def test_pdbqt_format_validation():
    # Legitimate receptor and ligand PDBQT
    v_rec, err_rec = validate_pdbqt_format(EGFR_4WKQ_RECEPTOR_PDBQT)
    assert v_rec is True
    assert err_rec is None

    v_lig, err_lig = validate_pdbqt_format(ERLOTINIB_LIGAND_PDBQT)
    assert v_lig is True
    assert err_lig is None

    # Empty string
    v_empty, err_empty = validate_pdbqt_format("")
    assert v_empty is False

    # Random text with no ATOM records
    v_bad, err_bad = validate_pdbqt_format("This is a random text file without coordinates")
    assert v_bad is False
    assert "no ATOM or HETATM" in err_bad

def test_sha256_checksum():
    text = "AIDD_SCIENTIFIC_REPRODUCIBILITY_2026"
    h1 = compute_sha256(text)
    h2 = compute_sha256(text)
    assert len(h1) == 64
    assert h1 == h2
    assert h1 != compute_sha256("OTHER_STRING")

if __name__ == "__main__":
    test_search_box_positive_bounds()
    test_pdbqt_format_validation()
    test_sha256_checksum()
    print("All Unit Tests Passed!")
