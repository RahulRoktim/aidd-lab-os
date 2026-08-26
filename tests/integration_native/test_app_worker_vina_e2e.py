import pytest
import os
from fastapi.testclient import TestClient
from app.main import app
from app.worker_client import get_worker_status

client = TestClient(app)


@pytest.mark.integration
def test_app_worker_vina_e2e_true():
    # 1. Skip if worker isn't running / native tools aren't present
    st = get_worker_status()
    if not st.get("connected"):
        pytest.skip("Scientific Worker is completely offline. Skipping true native E2E.")
    vina_capability = st.get("scientific_software", {}).get("autodock_vina", {})
    if not (
        vina_capability.get("installed")
        and vina_capability.get("identity_verified")
        and vina_capability.get("production_ready")
    ):
        pytest.skip("An identified native AutoDock Vina runtime is not available in the worker.")

    # 2. Read real benchmark assets
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    rec_path = os.path.join(base_dir, "benchmark_assets", "synthetic_4wkq_receptor_fixture.pdbqt")
    lig_path = os.path.join(base_dir, "benchmark_assets", "synthetic_ligand_fixture_b.pdbqt")

    if not os.path.exists(rec_path) or not os.path.exists(lig_path):
        pytest.skip("Benchmark PDBQT assets not found.")

    with open(rec_path, 'r', encoding='utf-8') as f:
        rec_content = f.read()
    with open(lig_path, 'r', encoding='utf-8') as f:
        lig_content = f.read()

    # 3. Create Project & Dataset explicitly
    proj_res = client.post("/api/projects", json={"name": "E2E Native Project"})
    assert proj_res.status_code == 200
    proj_id = proj_res.json()["id"]

    molecule_id = "E2E-NATIVE-1"
    ds_res = client.post(
        f"/api/projects/{proj_id}/molecules/import",
        json={
            "dataset_name": "Native docking integration fixture",
            "molecules": [{"id": molecule_id, "name": "Synthetic fixture record B", "smiles": "CCO"}],
        },
    )
    assert ds_res.status_code == 200
    ds_id = ds_res.json()["dataset_id"]

    # 4. Call real app path
    payload = {
        "input_dataset_id": ds_id,
        "result_origin": "COMPUTED",
        "receptor_pdbqt": rec_content,
        "prepared_ligands": [{"id": molecule_id, "pdbqt": lig_content}],
        "center_x": 22.4,
        "center_y": 0.8,
        "center_z": 52.5,
        "exhaustiveness": 8,
        "num_modes": 9,
        "seed": 42,
    }

    response = client.post(f"/api/projects/{proj_id}/experiments/docking", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert data["metrics"]["result_origin"] == "COMPUTED"
    assert data["metrics"]["worker_job_id"]
    assert data["metrics"]["worker_id"] == st["worker_id"]
    assert data["metrics"]["environment_sha256"]
    assert data["metrics"]["tool"] == "AutoDock Vina"
    assert data["metrics"]["tool_version"] == vina_capability["version"]
    assert data["metrics"]["vina_binary_sha256"] == vina_capability["binary_sha256"]
    assert data["metrics"]["vina_binary_sha256"] == data["metrics"]["vina_expected_binary_sha256"]
    assert data["metrics"]["vina_binary_digest_verified"] is True
    assert data["metrics"]["vina_path_verified"] is True
    assert data["metrics"]["vina_package_metadata_verified"] is True
    assert data["metrics"]["vina_version_output_sha256"] == vina_capability["version_output_sha256"]
    assert data["metrics"]["stdout_sha256"]
    assert data["metrics"]["output_pdbqt_hashes"]
    assert data["metrics"]["reproducibility_hash"]
    assert data["metrics"]["prepared_ligand_attestations"][0]["prepared_ligand_id"] == molecule_id
    assert data["metrics"]["prepared_ligand_attestations"][0]["ligand_output_integrity"]["verified"] is True
    assert data["metrics"]["is_native_vina_executed"] is True

    # 5. Assert the database records
    exp_id = data["experiment_id"]
    exp_res = client.get(f"/api/experiments/{exp_id}")
    assert exp_res.status_code == 200
    exp = exp_res.json()

    assert exp["status"] == "completed"
    assert exp["output_dataset_id"] == data["output_dataset_id"]
    assert exp["metrics"]["result_origin"] == "COMPUTED"
    assert exp["metrics"]["exit_code"] == 0
    assert exp["metrics"]["worker_id"] == st["worker_id"]
    assert exp["metrics"]["tool_version"] == vina_capability["version"]
    assert exp["metrics"]["vina_binary_sha256"] == vina_capability["binary_sha256"]
    assert exp["docking_results"][0]["result_origin"] == "COMPUTED"
    assert exp["docking_results"][0]["vina_version"] == vina_capability["version"]
