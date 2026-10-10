"""Routes behind the "Returns vs Volatility" dashboard chart."""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import risk_return


@pytest.fixture
def client():
    return TestClient(create_app())


def test_group_risk_return_passes_through(client, monkeypatch):
    def fake(slug, days, *, pricing_date=None):
        assert (slug, days) == ("family", 730)
        return {"group": slug, "points": [], "missing_members": []}

    monkeypatch.setattr(risk_return, "compute_group_risk_return", fake)

    resp = client.get("/performance-group/family/risk-return?days=730")

    assert resp.status_code == 200
    assert resp.json()["group"] == "family"


def test_group_risk_return_unknown_group_is_404(client, monkeypatch):
    def unknown(slug, days, *, pricing_date=None):
        raise ValueError(slug)

    monkeypatch.setattr(risk_return, "compute_group_risk_return", unknown)

    assert client.get("/performance-group/nope/risk-return").status_code == 404


@pytest.mark.parametrize("days", [0, 29, 3651])
def test_risk_return_window_is_bounded(client, days):
    assert client.get(f"/performance-group/family/risk-return?days={days}").status_code == 400
    assert client.get(f"/risk-return/benchmark?ticker=^FTSE&days={days}").status_code == 400


def test_benchmark_accepts_index_symbols(client, monkeypatch):
    def fake(ticker, days, *, pricing_date=None):
        return {"ticker": ticker, "period_return": 0.1, "annualised_return": None, "volatility": 0.12}

    monkeypatch.setattr(risk_return, "compute_benchmark_risk_return", fake)

    resp = client.get("/risk-return/benchmark", params={"ticker": "^ftse"})

    assert resp.status_code == 200
    assert resp.json()["ticker"] == "^FTSE"


@pytest.mark.parametrize("ticker", ["", "../etc", "^^FTSE", "A/B", "x" * 40])
def test_benchmark_rejects_bad_tickers(client, ticker):
    assert client.get("/risk-return/benchmark", params={"ticker": ticker}).status_code == 400


def test_benchmark_without_history_is_404(client, monkeypatch):
    monkeypatch.setattr(risk_return, "compute_benchmark_risk_return", lambda *a, **k: None)

    assert client.get("/risk-return/benchmark?ticker=VWRL.L").status_code == 404


def test_group_risk_return_includes_configured_risk_free_rate(client, monkeypatch):
    from backend.config import config

    def fake(slug, days, *, pricing_date=None):
        return {"group": slug, "points": [], "missing_members": []}

    monkeypatch.setattr(risk_return, "compute_group_risk_return", fake)
    monkeypatch.setattr(config, "risk_free_rate", 0.04)

    assert client.get("/performance-group/family/risk-return").json()["risk_free_rate"] == 0.04

    monkeypatch.setattr(config, "risk_free_rate", None)

    assert client.get("/performance-group/family/risk-return").json()["risk_free_rate"] == 0.0
