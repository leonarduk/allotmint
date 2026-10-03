from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config
from backend.routes import instrument

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
    monkeypatch.setattr("backend.routes.instrument.list_instruments", lambda: SAMPLE_INSTRUMENTS)
    client = TestClient(app)
    resp = client.get("/instrument/search", params={"q": "alpha"})
    assert resp.status_code == 200
    assert resp.json() == [SAMPLE_INSTRUMENTS[2]]

    resp_sector = client.get("/instrument/search", params={"q": "c", "sector": "Finance"})
    resp_region = client.get("/instrument/search", params={"q": "c", "region": "US"})
    assert resp_sector.json() == [SAMPLE_INSTRUMENTS[1]]
    assert resp_region.json() == [SAMPLE_INSTRUMENTS[1]]


def test_search_invalid_inputs(monkeypatch):
    app = FastAPI()
    app.include_router(instrument.router)
    monkeypatch.setattr("backend.routes.instrument.list_instruments", lambda: SAMPLE_INSTRUMENTS)
    client = TestClient(app)
    assert client.get("/instrument/search").status_code == 400
    assert client.get("/instrument/search", params={"q": "a", "sector": ""}).status_code == 400
    assert client.get("/instrument/search", params={"q": "a", "region": ""}).status_code == 400


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_validate_ticker_accepts():
    assert instrument._validate_ticker("ABC.L") is None


@pytest.mark.parametrize("bad", ["", ".L", ".UK"])
def test_validate_ticker_rejects(bad):
    with pytest.raises(HTTPException):
        instrument._validate_ticker(bad)


def _stub_owner_sources(monkeypatch, owner, raw_holdings, enriched_holdings, total=None):
    """Patch owner discovery (raw files) and the enriched portfolio builder."""
    portfolios = [{"owner": owner, "accounts": [{"account_type": "isa", "holdings": raw_holdings}]}]
    if total is None:
        total = sum(float(h.get("market_value_gbp") or 0.0) for h in enriched_holdings)
    built = {
        "owner": owner,
        "accounts": [{"account_type": "isa", "holdings": enriched_holdings}],
        "total_value_estimate_gbp": total,
    }
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: portfolios)
    monkeypatch.setattr("backend.routes.instrument.build_owner_portfolio", lambda *_a, **_k: built)


def test_positions_for_ticker_projects_enriched_rows(monkeypatch):
    enriched = [
        {
            "ticker": "ABC.L",
            "units": 2,
            "market_value_gbp": 22.0,
            "current_price_gbp": 11.0,
            "cost_basis_gbp": 20.0,
            "effective_cost_basis_gbp": 20.0,
            "gain_gbp": 2.0,
            "gain_pct": 10.0,
            "acquired_date": "2024-01-02",
            "days_held": 100,
            "cost_basis_source": "book",
        },
        {
            # Derived cost: no booked cost, effective cost from acquisition close.
            "ticker": "ABC.L",
            "units": 4,
            "market_value_gbp": 44.0,
            "cost_basis_gbp": 0.0,
            "effective_cost_basis_gbp": 32.0,
            "gain_gbp": 12.0,
            "gain_pct": 37.5,
            "cost_basis_source": "derived",
        },
        {"ticker": "OTHER.L", "units": 1, "market_value_gbp": 34.0},
    ]
    _stub_owner_sources(monkeypatch, "alex", [{"ticker": "ABC.L", "units": 2}], enriched)

    first, second = instrument._positions_for_ticker("ABC.L")

    assert first["unrealised_gain_gbp"] == first["gain_gbp"] == pytest.approx(2.0)
    assert first["cost_basis_gbp"] == pytest.approx(20.0)
    assert first["avg_cost_gbp"] == pytest.approx(10.0)
    assert first["current_price_gbp"] == pytest.approx(11.0)
    assert first["weight_pct"] == pytest.approx(22.0)
    assert first["acquired_date"] == "2024-01-02"
    assert first["days_held"] == 100
    assert second["cost_basis_gbp"] == pytest.approx(32.0)
    assert second["avg_cost_gbp"] == pytest.approx(8.0)
    assert second["gain_pct"] == pytest.approx(37.5)
    assert second["acquired_date"] is None


def test_positions_for_ticker_suspect_book_cost_is_unknown(monkeypatch):
    enriched = [
        {
            "ticker": "ABC.L",
            "units": 2,
            "market_value_gbp": 22.0,
            "cost_basis_gbp": 0.02,
            "gain_gbp": None,
            "gain_pct": None,
            "cost_basis_source": "book_suspect",
            "cost_basis_warning": "implied_unit_cost_out_of_band",
        }
    ]
    _stub_owner_sources(monkeypatch, "alex", [{"ticker": "ABC.L", "units": 2}], enriched)

    [position] = instrument._positions_for_ticker("ABC.L")

    assert position["market_value_gbp"] == pytest.approx(22.0)
    assert position["cost_basis_gbp"] is None
    assert position["avg_cost_gbp"] is None
    assert position["gain_gbp"] is None
    assert position["gain_pct"] is None
    assert position["cost_basis_source"] == "book_suspect"
    assert position["cost_basis_warning"] == "implied_unit_cost_out_of_band"


def test_positions_for_ticker_non_finite_values_become_none(monkeypatch):
    enriched = [{"ticker": "ABC.L", "units": 2, "market_value_gbp": float("nan"), "gain_pct": float("inf")}]
    _stub_owner_sources(monkeypatch, "alex", [{"ticker": "ABC.L", "units": 2}], enriched, total=0.0)

    [position] = instrument._positions_for_ticker("ABC.L")

    assert position["market_value_gbp"] is None
    assert position["gain_pct"] is None
    assert position["weight_pct"] is None


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
    assert 'class="dataframe prices"' in html
    assert 'class="dataframe positions"' in html


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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
        patch("backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df),
    ):
        client = _auth_client(app)
        resp_json = client.get("/instrument?ticker=ABC.L&days=1&format=json&base_currency=USD")
        resp_html = client.get("/instrument?ticker=ABC.L&days=1&format=html")

    assert resp_json.status_code == 200
    data = resp_json.json()
    assert data["ticker"] == "ABC.L"
    assert data["prices"][-1]["close_usd"] == pytest.approx(11.0 / 0.8)
    assert "USDGBP" in data["fx"]

    assert resp_html.status_code == 200
    assert "<table" in resp_html.text


def test_instrument_route_include_mini_query_param_via_http(monkeypatch):
    """``include_mini`` is a bare-signature Query param (no explicit param list
    on the ``@router.get`` decorator), so it's exposed the same way as every
    other query param on this route. Exercised through a real HTTP request via
    TestClient -- not a direct function call -- to prove it actually reaches
    the ASGI route, not just the Python function (#7081 review)."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
    ):
        client = _auth_client(app)
        resp_default = client.get("/instrument?ticker=ABC.L&days=1&format=json")
        resp_included = client.get("/instrument?ticker=ABC.L&days=1&format=json&include_mini=true")

    assert resp_default.status_code == 200
    assert "mini" not in resp_default.json()

    assert resp_included.status_code == 200
    data = resp_included.json()
    assert set(data["mini"]) == {"7", "30", "180"}
    assert data["mini"]["7"] == data["prices"][-7:]


def test_instrument_route_close_only_prices_converts_to_gbp(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2022-01-01", periods=2, freq="D"),
            "Close": [100.0, 110.0],
        }
    )

    def fake_fx(base, quote, start_date, end_date):
        dates = pd.date_range(start_date, end_date, freq="D")
        if dates.empty:
            dates = pd.to_datetime([start_date])
        rate = 0.8 if (base, quote) == ("USD", "GBP") else 1.0
        return pd.DataFrame({"Date": dates, "Rate": [rate] * len(dates)})

    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch(
            "backend.routes.instrument.get_security_meta",
            return_value={"currency": "USD"},
        ),
        patch("backend.routes.instrument.fetch_fx_rate_range", side_effect=fake_fx),
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=XYZ.N&days=2&format=json")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["prices"][-1]["close_gbp"] == pytest.approx(88.0)
    # Position figures come from the enriched holdings pipeline (#8533) and are
    # covered by tests/test_instrument_route.py.
    assert payload["positions"] == []
