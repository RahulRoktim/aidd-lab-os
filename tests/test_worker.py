"""
AIDD Lab OS - Phase 3: Scientific Worker & Execution Engine Audit Suite
Tests capability discovery, job lifecycle, native/fallback RDKit engine,
Vina docking output parser, 55-molecule diverse benchmark, and security controls.
"""

import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, '/working_dir/c_1ed089c83162bf3c/aidd_lab_os')

from aidd_worker.services import capability_service, environment_service, rdkit_service, vina_service, job_service
from aidd_worker.models import (
    DescriptorJobRequest, StandardizeJobRequest, DockingJobRequest,
    MoleculeInput, SearchBoxConfig, JobStatus
)
from app import worker_client

def run_worker_tests():
    print("================================================================================")
    print("STARTING AIDD SCIENTIFIC WORKER AUDIT SUITE (v1.3.0)")
    print("================================================================================")

    # 1. Test Capability Discovery (Non-faked detection)
    print("\n[TEST 1] Scientific Software Capability Discovery:")
    caps = capability_service.get_all_capabilities()
    print(f"  Worker ID: {caps['worker_id']}")
    print(f"  Platform: {caps['platform']['system']} ({caps['platform']['architecture']}), Python {caps['platform']['python_version']}, {caps['platform']['cpu_count']} Cores")
    print(f"  RDKit: Installed={caps['scientific_software']['rdkit']['installed']}, Backend={caps['scientific_software']['rdkit']['backend']}")
    print(f"  AutoDock Vina: Installed={caps['scientific_software']['autodock_vina']['installed']}, Path={caps['scientific_software']['autodock_vina']['path']}")
    print(f"  OpenBabel: Installed={caps['scientific_software']['openbabel']['installed']}")
    assert "scientific_software" in caps
    assert "rdkit" in caps["scientific_software"]
    assert "autodock_vina" in caps["scientific_software"]
    print("✓ [TEST 1 PASSED] Software discovery completed accurately.")

    # 2. Test Environment Capture
    print("\n[TEST 2] Computational Environment Capture:")
    env = environment_service.capture_full_environment()
    assert env["worker_id"] == caps["worker_id"]
    assert "core_libraries" in env
    print(f"  Captured {len(env['core_libraries'])} core scientific libraries.")
    print("✓ [TEST 2 PASSED] Environment metadata captured.")

    # 3. Test 55-Molecule Diversity Benchmark (14 Chemistry Classes)
    print("\n[TEST 3] 55-Molecule Comprehensive Benchmark Suite:")
    bench_res = rdkit_service.run_50_molecule_validation_suite()
    print(f"  Compounds Evaluated: {bench_res['total_compounds_tested']} across {bench_res['categories_tested']} chemical categories")
    print(f"  Success Rate: {bench_res['successful_count']} / {bench_res['total_compounds_tested']} ({bench_res['engine']})")
    assert bench_res["total_compounds_tested"] >= 50
    assert bench_res["successful_count"] == bench_res["total_compounds_tested"]
    assert bench_res["failed_count"] == 0
    assert bench_res["validation_passed"] is True
    print("✓ [TEST 3 PASSED] 55/55 diverse chemical structures verified.")

    # 4. Test Descriptor Job Execution & Artifact Generation
    print("\n[TEST 4] Descriptor Job Execution & Checksum Generation:")
    desc_req = DescriptorJobRequest(
        molecules=[
            MoleculeInput(id="LIG-101", name="Osimertinib", smiles="C=CC(=O)Nc1cc(Nc2nccc(n2)c3cn(C)c4ccccc34)c(OC)cc1N(C)CCN(C)C"),
            MoleculeInput(id="LIG-102", name="Gefitinib", smiles="COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"),
            MoleculeInput(id="LIG-FAIL", name="Invalid Radical", smiles="c1ccccc1[N+](=O)(=O)C(F)(F)(F)(F)")
        ],
        experiment_id="exp_test_desc_01"
    )
    job_desc = job_service.run_descriptor_job(desc_req)
    assert job_desc.status == JobStatus.COMPLETED
    assert job_desc.successful_count == 2
    assert job_desc.failed_count == 1
    assert len(job_desc.artifacts) >= 2
    assert job_desc.artifacts[-1].name == "checksums.sha256"
    assert len(job_desc.reproducibility_hash) == 64
    print(f"  Job ID: {job_desc.job_id} | Status: {job_desc.status} | Output Artifacts: {len(job_desc.artifacts)}")
    print("✓ [TEST 4 PASSED] Job execution, error trapping, and SHA-256 artifacts verified.")

    # 5. Test Standardization Job (Salt stripping & Neutralization)
    print("\n[TEST 5] Standardization Job Execution:")
    std_req = StandardizeJobRequest(
        molecules=[
            MoleculeInput(id="SALT-1", name="Flavopiridol HCl", smiles="CN1CCC(C(C1)O)c2c(c(c3c(c2O)c(=O)cc(o3)c4ccccc4Cl)O)O.Cl"),
            MoleculeInput(id="SALT-2", name="Sodium Acetate", smiles="CC(=O)O.[Na]")
        ],
        remove_salts=True,
        neutralize_charges=True
    )
    job_std = job_service.run_standardize_job(std_req)
    assert job_std.status == JobStatus.COMPLETED
    assert job_std.successful_count == 2
    for r in job_std.results:
        assert "." not in r["standardized_smiles"], f"Salt counterions must be stripped in {r['name']}!"
    print(f"  Desalted {job_std.successful_count} salt mixtures successfully.")
    print("✓ [TEST 5 PASSED] Molecular standardization job verified.")

    # 6. Test AutoDock Vina Output Log Parser & Search Box Validation
    print("\n[TEST 6] AutoDock Vina Log Parsing & Search Box Bounds:")
    poses = vina_service.parse_vina_log_output(vina_service.VINA_STANDARD_LOG_FIXTURE)
    assert len(poses) == 9, "Fixture must parse exactly 9 binding modes!"
    assert poses[0]["rank"] == 1
    assert poses[0]["affinity_kcal_mol"] == -10.4
    assert poses[0]["rmsd_lower_bound"] == 0.0
    assert poses[1]["affinity_kcal_mol"] == -9.8
    print(f"  Parsed {len(poses)} poses. Best Binding Energy: {poses[0]['affinity_kcal_mol']} kcal/mol.")

    # Test invalid search box rejection
    try:
        vina_service.execute_docking_job("job_invalid_sb", DockingJobRequest(
            receptor_pdbqt="HEADER",
            ligands=[{"id": "L1", "pdbqt": "ATOM"}],
            search_box=SearchBoxConfig(center_x=0.0, center_y=0.0, center_z=0.0, size_x=-5.0, size_y=20.0, size_z=20.0)
        ))
        assert False, "Negative search box size must be rejected!"
    except ValueError as e:
        print(f"  Successfully caught invalid search box: {e}")
    print("✓ [TEST 6 PASSED] Vina parser and search box boundary checks verified.")

    # 7. Test Live Worker REST API over HTTP
    print("\n[TEST 7] Worker REST API Communication over HTTP (Port 8001):")
    st = worker_client.get_worker_status()
    if not st.get("connected"):
        print("  Worker is offline, skipping live HTTP tests.")
        return

    assert st["connected"] is True, "Live worker must be connected on port 8001!"
    print(f"  Worker Status: {st['status']} (ID: {st['worker_id']})")
    
    # Test HTTP Job Proxy
    succ, http_job = worker_client.submit_descriptor_job([
        {"id": "HTTP-1", "name": "Caffeine", "smiles": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"}
    ])
    assert succ is True
    assert http_job["status"] == "COMPLETED"
    assert http_job["successful_count"] == 1
    print(f"  HTTP Job Submitted: {http_job['job_id']} -> Status: {http_job['status']}")
    print("✓ [TEST 7 PASSED] Live worker REST API verified.")

    # 8. Security Controls (Path Traversal Protection)
    print("\n[TEST 8] Security & Sandboxing Controls:")
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/jobs/test_job/artifacts/../../etc/passwd")
        urllib.request.urlopen(req)
        assert False, "Path traversal must be blocked!"
    except urllib.error.HTTPError as e:
        print(f"  Path traversal attempt successfully rejected with HTTP {e.code}.")
        assert e.code == 404
    print("✓ [TEST 8 PASSED] Path traversal protection verified.")

    print("\n================================================================================")
    print("ALL 8 SCIENTIFIC WORKER & RUNTIME AUDIT STAGES PASSED 100%!")
    print("================================================================================")

if __name__ == "__main__":
    run_worker_tests()
