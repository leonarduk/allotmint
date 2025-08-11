import datetime as dt
from pathlib import Path

from backend.common import metrics as metrics_mod
from backend.app import create_app
from backend.config import config
from fastapi.testclient import TestClient


def _sample_txs():
    return [
        {"date": "2024-01-01", "ticker": "AAA", "type": "BUY", "shares": 10, "amount_minor": 10000},
        {"date": "2024-02-01", "ticker": "AAA", "type": "SELL", "shares": 10, "amount_minor": 12000},
        {"date": "2024-03-01", "ticker": "BBB", "type": "BUY", "shares": 5, "amount_minor": 5000},
    ]


def test_turnover_and_holding_period(monkeypatch, tmp_path):
    monkeypatch.setattr(metrics_mod, "METRICS_DIR", tmp_path)
    txs = _sample_txs()
    turnover = metrics_mod.calculate_portfolio_turnover("test", txs, portfolio_value=100)
    assert turnover == (10000 + 12000 + 5000) / 100 / 100

    avg = metrics_mod.calculate_average_holding_period(
        "test", txs, as_of=dt.date(2024, 4, 1)
    )
    # periods: AAA 31 days, BBB 31 days -> average 31
    assert avg == 31

    metrics = metrics_mod.compute_and_store_metrics(
        "test", txs, as_of=dt.date(2024, 4, 1), portfolio_value=100
    )
    path = tmp_path / "test_metrics.json"
    assert path.exists()
    assert metrics["turnover"] == turnover
    assert metrics["average_holding_period"] == avg


def test_metrics_route(monkeypatch, tmp_path):
    monkeypatch.setattr(metrics_mod, "METRICS_DIR", tmp_path)
    monkeypatch.setattr(metrics_mod, "calculate_portfolio_turnover", lambda o, txs=None, portfolio_value=None: 2.0)
    monkeypatch.setattr(metrics_mod, "calculate_average_holding_period", lambda o, txs=None, as_of=None: 30.0)
    config.skip_snapshot_warm = True
    client = TestClient(create_app())
    resp = client.get("/metrics/foo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["turnover"] == 2.0
    assert data["average_holding_period"] == 30.0
    # file should be created
    assert (tmp_path / "foo_metrics.json").exists()
