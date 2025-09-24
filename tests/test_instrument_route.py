import pandas as pd
import pandas as pd
import pytest
from unittest.mock import patch
from datetime import date

from backend.app import create_app
from backend.config import config
from fastapi.testclient import TestClient


def _auth_client(app):
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


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
    client = _auth_client(app)
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
        client = _auth_client(app)
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
        client = _auth_client(app)
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
        client = _auth_client(app)
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
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    data = resp.json()
    pos = data["positions"][0]
    assert pos["unrealised_gain_gbp"] == pytest.approx(2.0)
    assert pos["gain_pct"] == pytest.approx(10.0)


def test_non_gbp_instrument_has_distinct_close(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [10.0, 11.0],
            "Close_gbp": [8.0, 8.8],
        }
    )
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch(
        "backend.routes.instrument.list_portfolios", return_value=[]
    ), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "USD"}
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.N&days=1&format=json")
    assert resp.status_code == 200
    prices = resp.json()["prices"]
    assert prices[-1]["close"] != prices[-1]["close_gbp"]


def test_intraday_route(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    class FakeTicker:
        def history(self, period: str, interval: str):
            return pd.DataFrame({
                "Datetime": [pd.Timestamp("2024-01-02T10:00:00")],
                "Close": [10.0],
            })

    with patch("backend.routes.instrument.yf.Ticker", return_value=FakeTicker()):
        client = _auth_client(app)
        resp = client.get("/instrument/intraday?ticker=ABC.L")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"][0]["close"] == pytest.approx(10.0)

def test_base_currency_param_gbp_to_usd(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    fx_df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Rate": [0.8, 0.8],
        }
    )
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch("backend.routes.instrument.list_portfolios", return_value=[]), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}
    ), patch(
        "backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df
    ):
        client = _auth_client(app)
        resp = client.get(
            "/instrument?ticker=ABC.L&days=1&format=json&base_currency=USD"
        )
    assert resp.status_code == 200
    data = resp.json()
    prices = data["prices"]
    assert prices[-1]["close_usd"] == pytest.approx(11.0 / 0.8)
    assert "USDGBP" in data["fx"]


def test_base_currency_param_usd_to_eur(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [10.0, 11.0],
            "Close_gbp": [8.0, 8.8],
        }
    )
    fx_df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Rate": [0.9, 0.9],
        }
    )
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch("backend.routes.instrument.list_portfolios", return_value=[]), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "USD"}
    ), patch(
        "backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df
    ):
        client = _auth_client(app)
        resp = client.get(
            "/instrument?ticker=ABC.N&days=1&format=json&base_currency=EUR"
        )
    assert resp.status_code == 200
    data = resp.json()
    prices = data["prices"]
    assert prices[-1]["close_eur"] == pytest.approx(8.8 / 0.9)
    assert "EURGBP" in data["fx"]
    assert "USDGBP" in data["fx"]


def test_base_currency_from_config(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "base_currency", "USD")
    app = create_app()
    df = _make_df()
    fx_df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Rate": [0.8, 0.8],
        }
    )
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch("backend.routes.instrument.list_portfolios", return_value=[]), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}
    ), patch(
        "backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    data = resp.json()
    prices = data["prices"]
    assert prices[-1]["close_usd"] == pytest.approx(11.0 / 0.8)
    assert data["base_currency"] == "USD"


def test_missing_history_returns_404(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    empty = pd.DataFrame()
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=empty
    ), patch("backend.routes.instrument.get_security_meta", return_value={}), patch(
        "backend.routes.instrument.list_portfolios", return_value=[]
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 404


def test_gbx_prices_scaled_and_cost_basis_fallback(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [100.0, 120.0],
        }
    )

    monkeypatch.setattr(
        "backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    monkeypatch.setattr(
        "backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBX"}
    )
    monkeypatch.setattr(
        "backend.routes.instrument.list_portfolios",
        lambda: [
            {
                "owner": "alex",
                "accounts": [
                    {
                        "account_type": "isa",
                        "holdings": [
                            {
                                "ticker": "ABC.L",
                                "quantity": 10,
                                "effective_cost_basis_gbp": 10.0,
                            }
                        ],
                    }
                ],
            }
        ],
    )

    client = _auth_client(app)
    resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    payload = resp.json()

    prices = payload["prices"]
    assert prices[-1]["close"] == pytest.approx(120.0)
    assert prices[-1]["close_gbp"] == pytest.approx(1.2)

    position = payload["positions"][0]
    assert position["market_value_gbp"] == pytest.approx(12.0)
    assert position["unrealised_gain_gbp"] == pytest.approx(2.0)
    assert position["gain_pct"] == pytest.approx(20.0)


def test_base_currency_fetch_failure_is_resilient(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()

    monkeypatch.setattr(
        "backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df
    )
    monkeypatch.setattr(
        "backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBP"}
    )
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: [])

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.instrument.fetch_fx_rate_range", _boom)

    client = _auth_client(app)
    resp = client.get("/instrument?ticker=ABC.L&days=1&format=json&base_currency=USD")
    assert resp.status_code == 200
    payload = resp.json()

    last_price = payload["prices"][-1]
    assert "close_usd" not in last_price
    assert payload.get("fx", {}) == {}
