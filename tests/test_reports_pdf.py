import pytest
from fastapi.testclient import TestClient

import pytest

import backend.common.alerts as alerts
from backend import config as backend_config
import backend.reports as reports


@pytest.fixture
def client():
    """Return an authenticated TestClient with offline mode enabled."""

    previous = backend_config.config.offline_mode
    backend_config.config.offline_mode = True
    from backend.local_api.main import app

    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    alerts.config.sns_topic_arn = None
    try:
        yield client
    finally:
        backend_config.config.offline_mode = previous


def test_report_pdf(client, monkeypatch):
    """PDF reports require reportlab; otherwise a RuntimeError is raised."""

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

    data = reports.compile_report("test")
    if reports.canvas is None:
        with pytest.raises(RuntimeError, match="reportlab is required for PDF output"):
            reports.report_to_pdf(data)
        return

    pdf = reports.report_to_pdf(data)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100

