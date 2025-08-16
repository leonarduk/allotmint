from fastapi.testclient import TestClient

from backend.local_api.main import app

client = TestClient(app)


def test_scenario_route():
    resp = client.get("/scenario?ticker=VWRL.L&pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "owner" in first
        assert "total_value_estimate_gbp" in first
