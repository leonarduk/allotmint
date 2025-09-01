from fastapi.testclient import TestClient

from backend.local_api.main import app


def _auth_client():
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_scenario_route():
    client = _auth_client()
    resp = client.get("/scenario?ticker=VWRL.L&pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "owner" in first
        assert "baseline_total_value_gbp" in first
        assert "shocked_total_value_gbp" in first
        assert "delta_gbp" in first
