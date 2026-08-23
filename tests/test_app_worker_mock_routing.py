from fastapi.testclient import TestClient
from app.main import app
import os
import json

client = TestClient(app)

def test_app_worker_vina_e2e(monkeypatch):
    from app.worker_client import worker_client
    def mock_submit(payload, timeout):
        if payload.get("receptor_pdbqt") and payload.get("ligands") and payload.get("execution_mode") == "NATIVE":
            return {
                "status": "COMPLETED",
                "exit_code": 0,
                "results": [{"docking_score": -9.5}],
                "failures": []
            }
        return {"status": "FAILED"}
    monkeypatch.setattr(worker_client, "submit_docking_job", mock_submit)

    payload = {
        "input_dataset_id": "mock_id",
        "result_origin": "COMPUTED",
        "execution_mode": "NATIVE",
        "receptor_pdbqt": "mock_receptor",
        "prepared_ligands": [{"id": "L1", "pdbqt": "mock_ligand"}]
    }

    response = client.post("/api/projects/mock_proj/experiments/docking", json=payload)
    assert response.status_code == 200
    assert response.json()["exit_code"] == 0
    assert response.json()["best_docking_score"] == -9.5
