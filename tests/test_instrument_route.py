import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from datetime import date

from backend.app import create_app
from backend.config import config


def _make_df():
    return pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [10.0, 11.0],
            "Close_gbp": [10.0, 11.0],
        }
    )


@pytest.mark.parametrize("bad", ["", ".L", ".UK"])
def test_invalid_ticker_rejected(monkeypatch, bad):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    client = TestClient(app)
    resp = client.get(f"/instrument?ticker={bad}&days=1&format=json")
    assert resp.status_code == 400


def test_full_history_json(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ) as mock_load, patch(
        "backend.routes.instrument.list_portfolios",
        return_value=[
            {
                "owner": "alex",
                "accounts": [
                    {
                        "account_type": "isa",
                        "holdings": [{"ticker": "ABC.L", "units": 2}],
                    }
                ],
            }
        ],
    ), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}
    ):
        client = TestClient(app)
        resp = client.get("/instrument?ticker=ABC.L&days=0&format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "ABC.L"
    assert data["rows"] == 2
    assert data["positions"][0]["owner"] == "alex"
    assert data["currency"] == "GBP"
    assert mock_load.call_args.kwargs["start_date"] == date(1900, 1, 1)


def test_html_response(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch("backend.routes.instrument.list_portfolios", return_value=[]), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}
    ):
        client = TestClient(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=html")
    assert resp.status_code == 200
    text = resp.text
    assert "<table" in text
    assert "ABC.L" in text


def test_positions_scaled(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch(
        "backend.routes.instrument.list_portfolios",
        return_value=[
            {
                "owner": "alex",
                "accounts": [
                    {
                        "account_type": "isa",
                        "holdings": [
                            {"ticker": "ABC.L", "units": 2, "gain_gbp": 4}
                        ],
                    }
                ],
            }
        ],
    ), patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}), patch(
        "backend.routes.instrument.get_scaling_override", return_value=0.5
    ):
        client = TestClient(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    data = resp.json()
    pos = data["positions"][0]
    assert pos["market_value_gbp"] == pytest.approx(11.0)
    assert pos["unrealised_gain_gbp"] == pytest.approx(2.0)
    prices = data["prices"]
    assert prices[-1]["close_gbp"] == pytest.approx(5.5)


def test_positions_gain_from_cost(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch(
        "backend.routes.instrument.list_portfolios",
        return_value=[
            {
                "owner": "alex",
                "accounts": [
                    {
                        "account_type": "isa",
                        "holdings": [
                            {
                                "ticker": "ABC.L",
                                "units": 2,
                                "cost_basis_gbp": 20.0,
                            }
                        ],
                    }
                ],
            }
        ],
    ), patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}):
        client = TestClient(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    data = resp.json()
    pos = data["positions"][0]
    assert pos["unrealised_gain_gbp"] == pytest.approx(2.0)
    assert pos["gain_pct"] == pytest.approx(10.0)
