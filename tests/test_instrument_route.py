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


_SEARCH_FIXTURES = [
    {
        "ticker": "ALPHA.L",
        "name": "Alpha Industries",
        "sector": "Technology",
        "region": "UK",
    },
    {
        "ticker": "BETA.L",
        "name": "Beta Alpha Holdings",
        "sector": "Finance",
        "region": "US",
    },
    {
        "ticker": "ALPHX.N",
        "name": "Alpha X",
        "sector": "Technology",
        "region": "US",
    },
]

_SEARCH_FIXTURES.extend(
    {
        "ticker": f"ALP{i:02d}.L",
        "name": f"Alpha Candidate {i}",
        "sector": "Technology" if i % 2 else "Finance",
        "region": "US" if i % 3 else "UK",
    }
    for i in range(1, 25)
)


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "alpha", "sector": ""},
        {"q": "alpha", "region": ""},
    ],
)
def test_instrument_search_rejects_blank_inputs(monkeypatch, params):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    with patch("backend.routes.instrument.list_instruments", return_value=_SEARCH_FIXTURES):
        client = _auth_client(app)
        resp = client.get("/instrument/search", params=params)

    assert resp.status_code == 400


def test_instrument_search_filters_by_sector_and_region(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    with patch("backend.routes.instrument.list_instruments", return_value=_SEARCH_FIXTURES):
        client = _auth_client(app)
        resp_sector = client.get(
            "/instrument/search", params={"q": "alpha", "sector": "Technology"}
        )
        resp_region = client.get(
            "/instrument/search", params={"q": "alpha", "region": "US"}
        )

    assert resp_sector.status_code == 200
    sector_rows = resp_sector.json()
    assert sector_rows
    assert all(row["sector"] == "Technology" for row in sector_rows)
    assert "BETA.L" not in {row["ticker"] for row in sector_rows}

    assert resp_region.status_code == 200
    region_rows = resp_region.json()
    assert region_rows
    assert all(row["region"] == "US" for row in region_rows)
    assert "ALPHA.L" not in {row["ticker"] for row in region_rows}


def test_instrument_search_caps_results(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    with patch("backend.routes.instrument.list_instruments", return_value=_SEARCH_FIXTURES):
        client = _auth_client(app)
        resp = client.get("/instrument/search", params={"q": "alpha"})

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 20

    expected = [
        inst["ticker"]
        for inst in _SEARCH_FIXTURES
        if "alpha" in (inst.get("ticker", "").lower() + inst.get("name", "").lower())
    ][:20]
    assert [row["ticker"] for row in rows] == expected


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


def test_intraday_route_history_error(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    class FakeTicker:
        def history(self, period: str, interval: str):
            raise RuntimeError("history boom")

    with patch("backend.routes.instrument.yf.Ticker", return_value=FakeTicker()):
        client = _auth_client(app)
        resp = client.get("/instrument/intraday?ticker=ABC.L")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "history boom"


def test_intraday_route_history_empty(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    class FakeTicker:
        def history(self, period: str, interval: str):
            return pd.DataFrame()

    with patch("backend.routes.instrument.yf.Ticker", return_value=FakeTicker()):
        client = _auth_client(app)
        resp = client.get("/instrument/intraday?ticker=ABC.L")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "No intraday data for ABC.L"


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
