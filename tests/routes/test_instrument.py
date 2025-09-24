import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.routes import instrument
from backend.app import create_app
from backend.config import config


SAMPLE_INSTRUMENTS = [
    {"ticker": "ABC.L", "name": "ABC Company", "sector": "Tech", "region": "UK"},
    {"ticker": "XYZ.N", "name": "XYZ Corp", "sector": "Finance", "region": "US"},
    {"ticker": "ALPHA.L", "name": "Alpha Inc", "sector": "Tech", "region": "UK"},
]


def _auth_client(app: FastAPI) -> TestClient:
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [10.0, 11.0],
            "Close_gbp": [10.0, 11.0],
        }
    )


# ---------------------------------------------------------------------------
# /instrument/search
# ---------------------------------------------------------------------------

def test_search_valid_and_filters(monkeypatch):
    app = FastAPI()
    app.include_router(instrument.router)
    monkeypatch.setattr(
        "backend.routes.instrument.list_instruments", lambda: SAMPLE_INSTRUMENTS
    )
    client = TestClient(app)
    resp = client.get("/instrument/search", params={"q": "alpha"})
    assert resp.status_code == 200
    assert resp.json() == [SAMPLE_INSTRUMENTS[2]]

    resp_sector = client.get(
        "/instrument/search", params={"q": "c", "sector": "Finance"}
    )
    resp_region = client.get(
        "/instrument/search", params={"q": "c", "region": "US"}
    )
    assert resp_sector.json() == [SAMPLE_INSTRUMENTS[1]]
    assert resp_region.json() == [SAMPLE_INSTRUMENTS[1]]


def test_search_invalid_inputs(monkeypatch):
    app = FastAPI()
    app.include_router(instrument.router)
    monkeypatch.setattr(
        "backend.routes.instrument.list_instruments", lambda: SAMPLE_INSTRUMENTS
    )
    client = TestClient(app)
    assert client.get("/instrument/search").status_code == 400
    assert (
        client.get("/instrument/search", params={"q": "a", "sector": ""}).status_code
        == 400
    )
    assert (
        client.get("/instrument/search", params={"q": "a", "region": ""}).status_code
        == 400
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_validate_ticker_accepts():
    assert instrument._validate_ticker("ABC.L") is None


@pytest.mark.parametrize("bad", ["", ".L", ".UK"])
def test_validate_ticker_rejects(bad):
    with pytest.raises(HTTPException):
        instrument._validate_ticker(bad)


def test_positions_for_ticker_gain_and_cost(monkeypatch):
    portfolios = [
        {
            "owner": "alex",
            "accounts": [
                {
                    "account_type": "isa",
                    "holdings": [
                        {"ticker": "ABC.L", "units": 1, "gain_gbp": 5, "gain_pct": 50},
                        {"ticker": "ABC.L", "units": 2, "cost_basis_gbp": 20},
                    ],
                }
            ],
        }
    ]
    monkeypatch.setattr(
        "backend.routes.instrument.list_portfolios", lambda: portfolios
    )
    positions = instrument._positions_for_ticker("ABC.L", last_close=11.0)
    assert len(positions) == 2
    first, second = positions
    assert first["unrealised_gain_gbp"] == 5
    assert second["unrealised_gain_gbp"] == pytest.approx(2.0)
    assert second["gain_pct"] == pytest.approx(10.0)


def test_render_html_contains_tables():
    df = _make_df()
    positions = [
        {
            "owner": "alex",
            "account": "isa",
            "units": 1,
            "market_value_gbp": 11.0,
            "unrealised_gain_gbp": 1.0,
            "gain_pct": 10.0,
        }
    ]
    html = instrument._render_html("ABC.L", df, positions, window_days=30)
    assert "class=\"dataframe prices\"" in html
    assert "class=\"dataframe positions\"" in html


# ---------------------------------------------------------------------------
# /instrument route
# ---------------------------------------------------------------------------

def test_instrument_route_json_html_and_base_currency(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    fx_df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Rate": [0.8, 0.8],
        }
    )
    portfolios = [
        {
            "owner": "alex",
            "accounts": [
                {"account_type": "isa", "holdings": [{"ticker": "ABC.L", "units": 2}]}
            ],
        }
    ]
    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch(
        "backend.routes.instrument.list_portfolios", return_value=portfolios
    ), patch(
        "backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}
    ), patch(
        "backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df
    ):
        client = _auth_client(app)
        resp_json = client.get(
            "/instrument?ticker=ABC.L&days=1&format=json&base_currency=USD"
        )
        resp_html = client.get("/instrument?ticker=ABC.L&days=1&format=html")

    assert resp_json.status_code == 200
    data = resp_json.json()
    assert data["ticker"] == "ABC.L"
    assert data["prices"][-1]["close_usd"] == pytest.approx(11.0 / 0.8)
    assert "USDGBP" in data["fx"]

    assert resp_html.status_code == 200
    assert "<table" in resp_html.text


def test_instrument_route_close_only_prices_populates_positions(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2022-01-01", periods=2, freq="D"),
            "Close": [100.0, 110.0],
        }
    )

    portfolios = [
        {
            "owner": "sam",
            "accounts": [
                {
                    "account_type": "general",
                    "holdings": [
                        {"ticker": "XYZ.N", "units": 2, "cost_basis_gbp": 150.0}
                    ],
                }
            ],
        }
    ]

    def fake_fx(base, quote, start_date, end_date):
        dates = pd.date_range(start_date, end_date, freq="D")
        if dates.empty:
            dates = pd.to_datetime([start_date])
        rate = 0.8 if (base, quote) == ("USD", "GBP") else 1.0
        return pd.DataFrame({"Date": dates, "Rate": [rate] * len(dates)})

    with patch(
        "backend.routes.instrument.load_meta_timeseries_range", return_value=df
    ), patch(
        "backend.routes.instrument.list_portfolios", return_value=portfolios
    ), patch(
        "backend.routes.instrument.get_security_meta",
        return_value={"currency": "USD"},
    ), patch(
        "backend.routes.instrument.fetch_fx_rate_range", side_effect=fake_fx
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=XYZ.N&days=2&format=json")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["prices"][-1]["close_gbp"] == pytest.approx(88.0)
    assert len(payload["positions"]) == 1
    position = payload["positions"][0]
    assert position["market_value_gbp"] == pytest.approx(176.0)
    assert position["unrealised_gain_gbp"] == pytest.approx(26.0)
    assert position["gain_pct"] == pytest.approx(17.333333, rel=1e-3)
