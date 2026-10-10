"""/screener/risk-return: Sharpe, volatility and worst fall per window (allotmint#10607).

The engine lives in allotmint-pro (allotmint-pro#724); these tests use a stand-in for
``risk_return_for_tickers`` so they run with or without the private package installed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import core_feature_unavailable_handler
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.routes import screener

PAYLOAD = {
    "as_of": "2026-10-08",
    "risk_free": {"3": 0.0449, "5": 0.0369, "10": 0.0204},
    "method": "Weekly returns; risk-free = mean Bank Rate over the window.",
    "rows": [
        {
            "ticker": "VUSA.L",
            "name": "Vanguard S&P 500 UCITS ETF",
            "currency": "GBP",
            "currency_source": "metadata",
            "return_basis": "partial",
            "first_date": "2013-05-22",
            "last_date": "2026-10-08",
            "windows": {
                "3": {
                    "gbp": {"return": 0.18, "volatility": 0.12, "sharpe": 1.15, "max_drawdown": -0.19},
                    "local": {"return": 0.18, "volatility": 0.12, "sharpe": 1.15, "max_drawdown": -0.19},
                },
                "5": None,
                "10": None,
            },
            "notes": [],
        }
    ],
    "missing": ["XYZ.L"],
    "fetched": [],
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(screener.router)
    app.add_exception_handler(CoreFeatureUnavailableError, core_feature_unavailable_handler)
    return TestClient(app)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(tickers, years=(3, 5, 10), fetch_missing=False, max_fetch=25):
        seen.append({"tickers": tickers, "years": years, "fetch_missing": fetch_missing, "max_fetch": max_fetch})
        return PAYLOAD

    monkeypatch.setattr(screener, "risk_return_for_tickers", fake)
    return seen


def test_returns_402_without_the_pro_module(monkeypatch):
    monkeypatch.setattr(screener, "risk_return_for_tickers", None)

    resp = _client().get("/screener/risk-return", params={"tickers": "VUSA.L"})

    assert resp.status_code == 402
    assert "Risk/return screen" in resp.json()["detail"]


def test_gate_is_checked_before_the_tickers(monkeypatch):
    """An empty ticker list still answers 402 when gated, so it can serve as a cheap probe."""

    monkeypatch.setattr(screener, "risk_return_for_tickers", None)

    assert _client().get("/screener/risk-return", params={"tickers": ""}).status_code == 402


def test_passes_through_the_engine_payload(calls):
    resp = _client().get("/screener/risk-return", params={"tickers": " vusa.l ,XYZ.L,VUSA.L"})

    assert resp.status_code == 200
    assert resp.json() == PAYLOAD
    assert calls == [
        {"tickers": ["VUSA.L", "XYZ.L"], "years": [3, 5, 10], "fetch_missing": False, "max_fetch": 25},
    ]


def test_forwards_years_and_fetch_options(calls):
    resp = _client().get(
        "/screener/risk-return",
        params={"tickers": "SPY", "years": "10,3", "fetch_missing": "true", "max_fetch": 5},
    )

    assert resp.status_code == 200
    assert calls[-1] == {"tickers": ["SPY"], "years": [3, 10], "fetch_missing": True, "max_fetch": 5}


@pytest.mark.parametrize("years", ["", "three", "0,5", "3,31"])
def test_rejects_invalid_years(calls, years):
    resp = _client().get("/screener/risk-return", params={"tickers": "SPY", "years": years})

    assert resp.status_code == 400
    assert calls == []


def test_rejects_a_blank_ticker_list(calls):
    assert _client().get("/screener/risk-return", params={"tickers": " , "}).status_code == 400
    assert calls == []


def test_caps_max_fetch(calls):
    resp = _client().get("/screener/risk-return", params={"tickers": "SPY", "max_fetch": 26})

    assert resp.status_code == 422
    assert calls == []


def test_maps_an_engine_value_error_to_400(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ValueError("unknown window")

    monkeypatch.setattr(screener, "risk_return_for_tickers", boom)

    resp = _client().get("/screener/risk-return", params={"tickers": "SPY"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown window"
