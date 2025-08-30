import pytest
from fastapi.testclient import TestClient

import backend.common.alerts as alerts
from backend import config as backend_config


@pytest.fixture(scope="module")
def client():
    """Return an authenticated TestClient with offline mode enabled."""

    previous = backend_config.config.offline_mode
    backend_config.config.offline_mode = True
    from backend.local_api.main import app

    client = TestClient(app)
    token = client.post(
        "/token", data={"username": "testuser", "password": "password"}
    ).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    alerts.config.sns_topic_arn = None
    try:
        yield client
    finally:
        backend_config.config.offline_mode = previous


def test_report_pdf(client, monkeypatch):
    """PDF reports should be generated using reportlab."""

    def fake_load_transactions(owner):
        return [
            {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000},
            {"date": "2024-01-02", "type": "DIVIDEND", "amount_minor": 500},
        ]

    def fake_performance(owner):
        return {
            "history": [{"date": "2024-01-02", "cumulative_return": 0.1}],
            "max_drawdown": -0.05,
        }

    monkeypatch.setattr("backend.reports._load_transactions", fake_load_transactions)
    monkeypatch.setattr(
        "backend.common.portfolio_utils.compute_owner_performance", fake_performance
    )

    resp = client.get("/reports/test?format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 100

