import os
import pytest
import requests


@pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="Live tests disabled")
def test_health_endpoint():
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    resp = requests.get(f"{base_url}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
