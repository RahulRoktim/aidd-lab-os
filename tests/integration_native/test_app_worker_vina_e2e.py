import pytest
import os
import json
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
    if not st.get("scientific_software", {}).get("autodock_vina", {}).get("installed"):
        pytest.skip("AutoDock Vina is not natively available in worker. Skipping true native E2E.")

    # 2. Read real benchmark assets
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    rec_path = os.path.join(base_dir, "benchmark_assets", "4wkq_receptor.pdbqt")
    lig_path = os.path.join(base_dir, "benchmark_assets", "erlotinib_ligand.pdbqt")

    if not os.path.exists(rec_path) or not os.path.exists(lig_path):
        pytest.skip("Benchmark PDBQT assets not found.")

    with open(rec_path, 'r', encoding='utf-8') as f:
        rec_content = f.read()
    with open(lig_path, 'r', encoding='utf-8') as f:
        lig_content = f.read()

    # 3. Create Project & Dataset explicitly
    proj_res = client.post("/api/projects", json={"name": "E2E Native Project"})
    assert proj_res.status_code == 200
    proj_id = proj_res.json()["project_id"]

    csv_data = "SMILES,ID\nC,M1"
    ds_res = client.post(f"/api/projects/{proj_id}/import_csv", files={"file": ("test.csv", csv_data.encode())})
    assert ds_res.status_code == 200
    ds_id = ds_res.json()["dataset_id"]

    # 4. Call real app path
    payload = {
        "input_dataset_id": ds_id,
        "result_origin": "COMPUTED",
        "execution_mode": "NATIVE",
        "receptor_pdbqt": rec_content,
        "prepared_ligands": [{"id": "Erlotinib", "pdbqt": lig_content}]
    }

    response = client.post(f"/api/projects/{proj_id}/experiments/docking", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["exit_code"] == 0
    assert data["metrics"]["result_origin"] == "COMPUTED"
    assert "worker_job_id" in data["metrics"]
    assert "environment_sha256" in data["metrics"]
    assert data["metrics"]["is_native_vina_executed"] is True
