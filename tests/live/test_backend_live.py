import os

import pytest
import requests


@pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="Live tests disabled")
def test_health_endpoint():
    base_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
    except requests.exceptions.RequestException as exc:
        pytest.skip(f"Backend unavailable at {base_url}: {exc}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
