from fastapi.testclient import TestClient
from app.main import app
from app import services

client = TestClient(app)

def test_app_worker_vina_e2e(monkeypatch):
    captured = {}

    def mock_run(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "exit_code": 0, "best_docking_score": -9.5}

    monkeypatch.setattr(services, "import_or_run_docking", mock_run)

    payload = {
        "input_dataset_id": "mock_id",
        "result_origin": "COMPUTED",
        "receptor_pdbqt": "mock_receptor",
        "prepared_ligands": [{"id": "L1", "pdbqt": "mock_ligand"}]
    }

    response = client.post("/api/projects/mock_proj/experiments/docking", json=payload)
    assert response.status_code == 200
    assert response.json()["exit_code"] == 0
    assert response.json()["best_docking_score"] == -9.5
    assert captured["result_origin"] == "COMPUTED"
    assert captured["receptor_pdbqt"] == "mock_receptor"
    assert captured["prepared_ligands"] == [{"id": "L1", "pdbqt": "mock_ligand"}]
