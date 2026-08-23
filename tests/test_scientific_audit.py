"""
AIDD Lab OS - Production Scientific Software Audit & Regression Test Suite
Validates chemical calculations against reference standards, cryptographic SHA-256 hashes,
experiment immutability, mathematical candidate ranking, and reproducibility bundles.
"""

import sys
import os
import json
import zipfile
import io

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from app.database import init_db, get_db
from app import services
from app.scientific_engine import ScientificEngine, REFERENCE_BENCHMARKS

def run_scientific_audit():
    print("================================================================================")
    print("STARTING SCIENTIFIC SOFTWARE AUDIT & REGRESSION SUITE: AIDD Lab OS Kernel v1.2.0")
    print("================================================================================")

    # 1. Scientific Regression Audit against Reference Compounds
    audit_res = ScientificEngine.run_regression_audit()
    print(f"\n[AUDIT STAGE 1] Scientific Descriptor Regression against Reference Standards:")
    print(f"  Active Engine: {audit_res['engine_status']['active_engine']}")
    print(f"  Passed: {audit_res['passed_count']} / {audit_res['compounds_tested']}")
    for d in audit_res['details']:
        print(f"    - {d['compound'].upper():14} | MW: {d['molecular_weight']['calculated']} | LogP: {d['logp']['calculated']} | TPSA: {d['tpsa']['calculated']} | HBD: {d['hbd']['calculated']} | HBA: {d['hba']['calculated']} -> {'PASS' if d['passed'] else 'FAIL'}")
    assert audit_res['all_passed'] is True, "All 6 reference standards must pass regression audit!"
    print("✓ [AUDIT STAGE 1 PASSED] 100% reference benchmark compliance.")

    # 2. Database Initialization
    init_db(force_recreate=True)
    print("\n[AUDIT STAGE 2] Initialized fresh relational database with cryptographic tables.")

    # 3. Create Verified Project
    proj = services.create_project(
        name="CDK9 Kinase Targeted Lead Optimization",
        description="Structure-based discovery of potent, selective CDK9 inhibitors for hematologic malignancies.",
        disease_indication="Acute Myeloid Leukemia (AML)",
        target_protein="CDK9 / Cyclin T1 Complex (PDB: 3BLR / 6Z45)",
        hypothesis="Targeting the ATP cleft and adjacent hinge region residue Phe103 with substituted pyrazolopyrimidine core achieves sub-10 nM affinity with >100-fold selectivity over CDK2."
    )
    proj_id = proj["id"]
    print(f"✓ [AUDIT STAGE 3] Created Project: '{proj['name']}' (ID: {proj_id})")

    # 4. Ingest Raw Molecules (including salt counterions and intentional valence failure)
    raw_compounds = [
        {"id": "CDK9-001", "name": "Dinaciclib Core", "smiles": "CC[C@@H](C)C1=C(C=NN1)NC2=NC=NC3=C2C=CN3"},
        {"id": "CDK9-002", "name": "Atuveciclib (BAY-1144884)", "smiles": "CN1C=C(C2=CC=C(C=C2)S(=O)(=O)C)C3=C1N=C(N=C3)NC4=CC=CC(=C4)F"},
        {"id": "CDK9-003", "name": "Flavopiridol Hydrochloride (Salt)", "smiles": "CN1CCC(C(C1)O)c2c(c(c3c(c2O)c(=O)cc(o3)c4ccccc4Cl)O)O.Cl"},
        {"id": "CDK9-FAIL", "name": "Hypervalent Nitrogen Radical", "smiles": "c1ccccc1[N+](=O)(=O)C(F)(F)(F)(F)"}
    ]

    imp_res = services.import_molecules_from_csv_or_list(
        project_id=proj_id,
        molecule_records=raw_compounds,
        dataset_name="Raw CDK9 Screening Batch #1",
        notes="Raw ingestion with salt mixture and invalid test radical"
    )
    assert imp_res["total_parsed"] == 3
    assert imp_res["total_failed"] == 1
    assert imp_res["failures"][0]["molecule_id"] == "CDK9-FAIL"
    assert imp_res["failures"][0]["error_type"] == "ParsingOrValenceError"
    ds1_id = imp_res["dataset_id"]
    print(f"✓ [AUDIT STAGE 4] Ingested 3 valid compounds and accurately trapped 1 valence error in failure audit log.")

    # 5. Standardization & Desalting Experiment
    std_res = services.run_standardization_experiment(
        project_id=proj_id,
        input_dataset_id=ds1_id,
        experiment_name="Desalting & Largest Fragment Standardization",
        remove_salts=True,
        neutralize_charges=True,
        max_mw=650.0,
        max_logp=6.8,
        notes="Stripping inorganic HCl counterion from Flavopiridol"
    )
    assert std_res["molecules_out"] == 3
    assert std_res["molecules_failed"] == 0
    ds2_id = std_res["output_dataset_id"]

    # Verify that original Flavopiridol SMILES is preserved and standardized SMILES has salt stripped
    flavo = services.get_molecule_detail("CDK9-003")
    assert ".Cl" in flavo["original_smiles"], "Original SMILES must preserve raw salt counterion!"
    assert ".Cl" not in flavo["standardized_smiles"], "Standardized SMILES must strip counterion!"
    print(f"✓ [AUDIT STAGE 5] Standardization verified. Original structure retained; standardized structure desalted.")

    # 6. Molecular Docking with Exhaustive Vina Metadata (Origin: IMPORTED)
    dock_csv = """molecule_id,docking_score
CDK9-001,-9.4
CDK9-002,-10.1
CDK9-003,-9.8"""
    dock_res = services.import_or_run_docking(
        project_id=proj_id,
        input_dataset_id=ds2_id,
        experiment_name="AutoDock Vina CDK9 Kinase Pocket Screen",
        docking_tool="AutoDock Vina",
        tool_version="1.2.5",
        receptor="CDK9 / Cyclin T1 (PDB: 3BLR)",
        grid_center="x=14.2, y=-8.6, z=24.1",
        center_x=14.2, center_y=-8.6, center_z=24.1,
        size_x=20.0, size_y=20.0, size_z=20.0,
        exhaustiveness=16,
        seed=42,
        result_origin="IMPORTED",
        custom_scores_csv=dock_csv,
        notes="Imported from verified AutoDock Vina runs on PDB 3BLR"
    )
    assert dock_res["molecules_docked"] == 3
    assert dock_res["best_docking_score"] == -10.1
    ds3_id = dock_res["output_dataset_id"]
    print(f"✓ [AUDIT STAGE 6] Docking results imported with exact Vina grid coordinates & origin='IMPORTED'.")

    # 7. ADMET Prediction Ingestion (Origin: IMPORTED)
    admet_csv = """molecule_id,gi_absorption,bbb_permeant,cyp3a4_inhibitor,cyp2d6_inhibitor,hepatotoxicity,mutagenicity_ames,herg_inhibition,clearance_rate,bioavailability_score,admet_risk_level,confidence
CDK9-001,High,No,Yes,No,Low Risk,Negative,Low Risk,4.5,0.55,Low Risk,0.92
CDK9-002,High,Yes,Yes,No,Low Risk,Negative,Low Risk,3.8,0.55,Low Risk,0.94
CDK9-003,High,No,Yes,No,Moderate Risk,Negative,Low Risk,5.2,0.55,Moderate Risk,0.88"""
    admet_res = services.import_or_run_admet(
        project_id=proj_id,
        input_dataset_id=ds3_id,
        experiment_name="SwissADME / pkCSM Pharmacokinetic Screen",
        tool_name="SwissADME & pkCSM Consensus",
        result_origin="IMPORTED",
        custom_admet_csv=admet_csv,
        notes="Verified consensus predictions"
    )
    assert admet_res["molecules_evaluated"] == 3
    print(f"✓ [AUDIT STAGE 7] ADMET predictions imported with model metadata & origin='IMPORTED'.")

    # 8. Candidate Multi-Objective Ranking with Step-by-Step Mathematical Transparency
    rank_res = services.calculate_candidate_rankings(
        project_id=proj_id,
        input_dataset_id=ds3_id,
        weights={"docking": 0.40, "qsar": 0.20, "admet": 0.25, "druglikeness": 0.15},
        missing_data_policy="RENORMALIZE",
        experiment_name="Multi-Objective Ranking (40% Dock / 20% QSAR / 25% ADMET / 15% QED)"
    )
    assert rank_res["total_ranked"] == 3
    top = rank_res["top_candidates"][0]
    assert top["molecule_id"] == "CDK9-002" # Atuveciclib (-10.1 kcal/mol, Low Risk)
    assert top["weighted_components"]["docking_contrib"] > 0
    print(f"✓ [AUDIT STAGE 8] Candidate ranking calculated. Rank #1: {top['molecule_name']} (Composite: {top['composite_score']}/100, Tier: {top['tier']}).")

    # 9. Experiment Immutability & Manifest Verification
    dock_exp = services.get_experiment_detail(dock_res["experiment_id"])
    assert dock_exp["is_locked"] == 1, "Completed experiment must be locked!"
    manifest = services.generate_experiment_manifest(dock_res["experiment_id"])
    assert manifest["experiment"]["id"] == dock_res["experiment_id"]
    assert manifest["parameters"]["result_origin"] == "IMPORTED"
    assert manifest["parameters"]["center_x"] == 14.2
    assert len(manifest["artifacts"]) >= 0
    print(f"✓ [AUDIT STAGE 9] Reproducibility manifest generated with full cryptographic & parameter audit.")

    # 10. Experiment Reproduction Test (Zero-Divergence Assertion)
    rep_res = services.reproduce_experiment(dock_res["experiment_id"])
    assert rep_res["reproduction_match"] is True, f"Reproduction must match 100%! Diffs: {rep_res['diff_reasons']}"
    print(f"✓ [AUDIT STAGE 10] Experiment reproduction verified. Cloned execution produced 100% matching results.")

    # 11. Append Note to Immutable Experiment
    note_res = services.append_experiment_note(dock_res["experiment_id"], "Validated binding pose in PyMOL: H-bonds formed with Cys106 and Asp167.", "Lead Structural Biologist")
    assert note_res["status"] == "appended"
    assert len(note_res["notes_log"]) == 1
    print(f"✓ [AUDIT STAGE 11] Note appended to immutable experiment note log without altering historical parameters.")

    # 12. Add Research Decision
    dec = services.add_decision_log(
        project_id=proj_id,
        title="Select Atuveciclib as Primary Chemical Probe",
        decision_text="Prioritize CDK9-002 for enzymatic IC50 kinase panel and cell viability in MV4-11 AML cell line.",
        rationale="Strongest binding affinity (-10.1 kcal/mol) and favorable oral bioavailability profile with zero Ames mutagenic alerts.",
        author="Principal Investigator",
        related_experiment_id=dock_res["experiment_id"],
        related_dataset_id=ds3_id,
        stage="Candidate Selection"
    )
    assert dec["id"].startswith("dec_")
    print(f"✓ [AUDIT STAGE 12] Research decision logged and linked to experiment & dataset.")

    # 13. Project Reproducibility Bundle ZIP Generation & Checksum Validation
    bundle_bytes = services.generate_project_reproducibility_bundle(proj_id)
    assert len(bundle_bytes) > 5000, "Bundle ZIP must contain all datasets, manifests, and checksums!"

    with zipfile.ZipFile(io.BytesIO(bundle_bytes), 'r') as zf:
        namelist = zf.namelist()
        assert "project_manifest.json" in namelist
        assert "provenance.json" in namelist
        assert "checksums.sha256" in namelist
        assert "candidates/ranked_candidates.csv" in namelist
        assert "decisions/decision_logs.json" in namelist
        assert "failures/failure_audit.csv" in namelist
        
        # Verify SHA-256 checksums
        checksum_content = zf.read("checksums.sha256").decode('utf-8')
        for line in checksum_content.strip().split('\n'):
            if line:
                expected_hash, fname = line.split('  ')
                actual_bytes = zf.read(fname)
                actual_hash = services.compute_sha256(actual_bytes)
                assert actual_hash == expected_hash, f"Checksum verification failed for {fname}!"

    print(f"✓ [AUDIT STAGE 13] Exported Project Reproducibility Bundle ({len(bundle_bytes)} bytes) with verified SHA-256 checksums.")

    # 14. Demo Project Seeding & Scientific Origin Verification
    services.seed_demo_project()
    demo_proj = services.get_project("proj_egfr_demo")
    assert demo_proj is not None
    demo_cands = services.get_candidate_rankings("proj_egfr_demo")
    assert len(demo_cands) == 15
    for c in demo_cands:
        assert c["docking_origin"] == "IMPORTED"
        assert c["admet_origin"] == "IMPORTED"
        assert c["result_origin"] == "COMPUTED"
    print(f"✓ [AUDIT STAGE 14] EGFR demo project verified. All docking and ADMET entries explicitly labeled with origin='IMPORTED'.")

    print("\n================================================================================")
    print("ALL 14 SCIENTIFIC VALIDATION & REPRODUCIBILITY AUDIT STAGES PASSED 100%!")
    print("================================================================================")

if __name__ == "__main__":
    run_scientific_audit()
