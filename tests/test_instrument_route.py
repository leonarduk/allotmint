from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


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
        resp_sector = client.get("/instrument/search", params={"q": "alpha", "sector": "Technology"})
        resp_region = client.get("/instrument/search", params={"q": "alpha", "region": "US"})

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


def _raw_portfolios(owner: str, accounts: dict[str, list[dict]]) -> list[dict]:
    return [
        {
            "owner": owner,
            "accounts": [{"account_type": name, "holdings": holdings} for name, holdings in accounts.items()],
        }
    ]


def _enriched_portfolio(owner: str, accounts: dict[str, list[dict]]) -> dict:
    """Shape returned by ``build_owner_portfolio`` with pre-enriched rows."""
    out_accounts = [{"account_type": name, "holdings": holdings} for name, holdings in accounts.items()]
    total = sum(float(h.get("market_value_gbp") or 0.0) for a in out_accounts for h in a["holdings"])
    return {"owner": owner, "accounts": out_accounts, "total_value_estimate_gbp": total}


def test_full_history_json(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    raw = {"isa": [{"ticker": "ABC.L", "units": 2}]}
    enriched = {"isa": [{"ticker": "ABC.L", "units": 2, "market_value_gbp": 22.0}]}
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df) as mock_load,
        patch("backend.routes.instrument.list_portfolios", return_value=_raw_portfolios("alex", raw)),
        patch(
            "backend.routes.instrument.build_owner_portfolio",
            return_value=_enriched_portfolio("alex", enriched),
        ),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
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


def test_positions_not_rescaled_by_route(monkeypatch):
    """The enriched pipeline already applies scaling overrides when pricing a
    holding, so the route must pass its gain through untouched (#8533)."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    raw = {"isa": [{"ticker": "ABC.L", "units": 2}]}
    enriched = {
        "isa": [
            {
                "ticker": "ABC.L",
                "units": 2,
                "market_value_gbp": 11.0,
                "gain_gbp": 4.0,
                "gain_pct": 57.142857,
                "cost_basis_gbp": 7.0,
                "cost_basis_source": "book",
            }
        ]
    }
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=_raw_portfolios("alex", raw)),
        patch(
            "backend.routes.instrument.build_owner_portfolio",
            return_value=_enriched_portfolio("alex", enriched),
        ),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
        patch("backend.routes.instrument.get_scaling_override", return_value=0.5),
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    data = resp.json()
    pos = data["positions"][0]
    assert pos["market_value_gbp"] == pytest.approx(11.0)
    assert pos["unrealised_gain_gbp"] == pytest.approx(4.0)
    assert pos["gain_gbp"] == pytest.approx(4.0)
    assert pos["cost_basis_gbp"] == pytest.approx(7.0)
    assert pos["avg_cost_gbp"] == pytest.approx(3.5)
    assert data["prices"][-1]["close_gbp"] == pytest.approx(5.5)


def _fake_owner_builder(raw_accounts: dict[str, list[dict]], *, other_value: float = 0.0):
    """A ``build_owner_portfolio`` stand-in that runs the real ``enrich_holding``.

    Mirrors the account/total aggregation of the real builder; ``other_value``
    adds a non-matching cash row so weight_pct is a real fraction.
    """
    from backend.common.holding_utils import enrich_holding

    def build(owner, accounts_root=None, *, root=None, pricing_date=None):
        accounts = []
        for name, holdings in raw_accounts.items():
            enriched = [enrich_holding(h, date.today(), {}) for h in holdings]
            if other_value:
                enriched.append({"ticker": "CASH.GBP", "units": other_value, "market_value_gbp": other_value})
            accounts.append(
                {
                    "account_type": name,
                    "holdings": enriched,
                    "value_estimate_gbp": sum(float(h.get("market_value_gbp") or 0.0) for h in enriched),
                }
            )
        return {
            "owner": owner,
            "accounts": accounts,
            "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in accounts),
        }

    return build


def _patch_route_sources(monkeypatch, owner: str, raw: dict[str, list[dict]], builder) -> None:
    monkeypatch.setattr("backend.routes.instrument.build_owner_portfolio", builder)
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: _raw_portfolios(owner, raw))
    monkeypatch.setattr("backend.routes.instrument.load_meta_timeseries_range", lambda *a, **k: _make_df())
    monkeypatch.setattr("backend.routes.instrument.get_security_meta", lambda _t: {"currency": "GBP"})


def test_positions_match_holdings_pipeline(monkeypatch):
    """Positions on /instrument equal the /portfolio/{owner} holding row (#8533)."""
    from backend.common import holding_utils, portfolio_utils

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    # Current price 12.00 GBP; acquisition-date close 10.00 GBP. No network.
    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", lambda *a, **k: (12.0, "test"))
    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", lambda *a, **k: 10.0)

    raw = {"SIPP": [{"ticker": "ABC.L", "units": 73, "cost_basis_gbp": 730.0, "acquired_date": "2024-01-02"}]}
    builder = _fake_owner_builder(raw, other_value=124.0)
    _patch_route_sources(monkeypatch, "steve", raw, builder)
    monkeypatch.setattr("backend.common.portfolio.build_owner_portfolio", builder)

    app = create_app()
    client = _auth_client(app)
    instrument_resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    portfolio_resp = client.get("/portfolio/steve")

    assert instrument_resp.status_code == 200
    assert portfolio_resp.status_code == 200
    [pos] = instrument_resp.json()["positions"]
    portfolio = portfolio_resp.json()
    [row] = [h for a in portfolio["accounts"] for h in a["holdings"] if h["ticker"] == "ABC.L"]

    assert pos["owner"] == "steve"
    assert pos["account"] == "SIPP"
    assert pos["units"] == pytest.approx(row["units"])
    assert pos["market_value_gbp"] == pytest.approx(row["market_value_gbp"])
    assert pos["gain_gbp"] == pytest.approx(row["gain_gbp"])
    assert pos["unrealised_gain_gbp"] == pytest.approx(row["unrealised_gain_gbp"])
    assert pos["gain_pct"] == pytest.approx(row["gain_pct"])
    assert pos["cost_basis_gbp"] == pytest.approx(row["cost_basis_gbp"])
    assert pos["current_price_gbp"] == pytest.approx(row["current_price_gbp"])
    assert pos["acquired_date"] == row["acquired_date"]
    assert pos["days_held"] == row["days_held"]
    assert pos["cost_basis_source"] == row["cost_basis_source"] == "book"
    assert pos["weight_pct"] == pytest.approx(row["market_value_gbp"] / portfolio["total_value_estimate_gbp"] * 100)

    # The concrete figures too, so a regression shared by both paths is caught.
    assert pos["market_value_gbp"] == pytest.approx(876.0)
    assert pos["cost_basis_gbp"] == pytest.approx(730.0)
    assert pos["avg_cost_gbp"] == pytest.approx(10.0)
    assert pos["gain_gbp"] == pytest.approx(146.0)
    assert pos["gain_pct"] == pytest.approx(20.0)
    assert pos["weight_pct"] == pytest.approx(87.6)


def test_positions_unreliable_cost_is_unknown_not_zero(monkeypatch):
    """No booked cost and no acquisition date: the gain is unknown (None), never
    a confident 0.00 from cost == current price (#8283/#8471)."""
    from backend.common import holding_utils, portfolio_utils

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", lambda *a, **k: (6.11, "test"))
    raw = {"SIPP": [{"ticker": "AIGE.L", "units": 1322.0, "cost_basis_gbp": 0.0}]}
    _patch_route_sources(monkeypatch, "steve", raw, _fake_owner_builder(raw))

    app = create_app()
    resp = _auth_client(app).get("/instrument?ticker=AIGE.L&days=1&format=json")

    assert resp.status_code == 200
    [pos] = resp.json()["positions"]
    assert pos["market_value_gbp"] == pytest.approx(8077.42)
    assert pos["cost_basis_source"] == "unknown"
    assert pos["gain_gbp"] is None
    assert pos["unrealised_gain_gbp"] is None
    assert pos["gain_pct"] is None
    assert pos["cost_basis_gbp"] is None
    assert pos["avg_cost_gbp"] is None


def test_positions_one_row_per_account(monkeypatch):
    """Ticker matching is case-insensitive on both the raw files used for owner
    discovery and the enriched rows, and against the requested ticker."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    # Raw file carries a mixed-case ticker; the enriched rows differ in case.
    raw = {"sipp": [{"ticker": "Abc.l", "units": 3}]}
    enriched = {
        "isa": [{"ticker": "abc.L", "units": 2, "market_value_gbp": 20.0}],
        "sipp": [{"ticker": "ABC.L", "units": 3, "market_value_gbp": 30.0}, {"ticker": "XYZ.L", "units": 1}],
    }
    _patch_route_sources(monkeypatch, "alex", raw, lambda *a, **k: _enriched_portfolio("alex", enriched))

    app = create_app()
    resp = _auth_client(app).get("/instrument?ticker=aBc.L&days=1&format=json")

    assert resp.status_code == 200
    positions = resp.json()["positions"]
    assert [(p["account"], p["units"]) for p in positions] == [("isa", 2), ("sipp", 3)]
    assert [p["weight_pct"] for p in positions] == [pytest.approx(40.0), pytest.approx(60.0)]


@pytest.mark.parametrize("total", [0.0, None, "missing"])
def test_positions_weight_none_without_owner_total(monkeypatch, total):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    raw = {"isa": [{"ticker": "ABC.L", "units": 2}]}
    built = _enriched_portfolio("alex", {"isa": [{"ticker": "ABC.L", "units": 2, "market_value_gbp": 20.0}]})
    if total == "missing":
        del built["total_value_estimate_gbp"]
    else:
        built["total_value_estimate_gbp"] = total
    _patch_route_sources(monkeypatch, "alex", raw, lambda *a, **k: built)

    app = create_app()
    resp = _auth_client(app).get("/instrument?ticker=ABC.L&days=1&format=json")

    assert resp.status_code == 200
    [pos] = resp.json()["positions"]
    assert pos["market_value_gbp"] == pytest.approx(20.0)
    assert pos["weight_pct"] is None


@pytest.mark.parametrize("source", ["unknown", "book_suspect"])
def test_positions_unreliable_cost_nulls_gain_in_api(monkeypatch, source):
    """Even if an enriched row carried a gain alongside an unreliable cost, the
    API returns the gain fields as null so non-UI consumers are not misled."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    raw = {"isa": [{"ticker": "ABC.L", "units": 2}]}
    row = {
        "ticker": "ABC.L",
        "units": 2,
        "market_value_gbp": 22.0,
        "cost_basis_gbp": 22.0,
        "gain_gbp": 0.0,
        "unrealised_gain_gbp": 0.0,
        "gain_pct": 0.0,
        "cost_basis_source": source,
    }
    _patch_route_sources(monkeypatch, "alex", raw, lambda *a, **k: _enriched_portfolio("alex", {"isa": [row]}))

    app = create_app()
    resp = _auth_client(app).get("/instrument?ticker=ABC.L&days=1&format=json")

    assert resp.status_code == 200
    [pos] = resp.json()["positions"]
    assert pos["cost_basis_source"] == source
    assert pos["cost_basis_gbp"] is None
    assert pos["avg_cost_gbp"] is None
    assert pos["gain_gbp"] is None
    assert pos["unrealised_gain_gbp"] is None
    assert pos["gain_pct"] is None
    assert pos["market_value_gbp"] == pytest.approx(22.0)


@pytest.mark.parametrize("error", [FileNotFoundError("no plot"), ValueError("malformed account file")])
def test_positions_skip_owner_whose_portfolio_fails(monkeypatch, caplog, error):
    """One owner's portfolio failing to build is logged and skipped; the other
    owners' positions are still returned and the page does not 500."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    raw = {"isa": [{"ticker": "ABC.L", "units": 2}]}
    good = _enriched_portfolio("alex", {"isa": [{"ticker": "ABC.L", "units": 2, "market_value_gbp": 20.0}]})

    def build(owner, *a, **k):
        if owner == "ghost":
            raise error
        return good

    _patch_route_sources(monkeypatch, "alex", raw, build)
    monkeypatch.setattr(
        "backend.routes.instrument.list_portfolios",
        lambda: _raw_portfolios("ghost", raw) + _raw_portfolios("alex", raw),
    )

    app = create_app()
    with caplog.at_level("WARNING", logger="backend.routes.instrument"):
        resp = _auth_client(app).get("/instrument?ticker=ABC.L&days=1&format=json")

    assert resp.status_code == 200
    assert [p["owner"] for p in resp.json()["positions"]] == ["alex"]
    assert any("ghost" in r.getMessage() and "ABC.L" in r.getMessage() for r in caplog.records)


def test_positions_scaling_override_applied_once(monkeypatch):
    """The holdings pipeline applies ``get_scaling_override`` when it prices a
    holding (holding_utils._get_price_for_date_scaled), so the route must not
    scale positions again. Runs the real ``enrich_holding`` against a raw
    pence-scale ``Close`` series with a 0.01 override; no network."""
    from backend.common import holding_utils, portfolio_utils

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    history = pd.DataFrame({"Date": [pd.Timestamp(date.today())], "Close": [1000.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: history)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 0.01)
    # Same override seen by the route's own price-series handling.
    monkeypatch.setattr("backend.routes.instrument.get_scaling_override", lambda *a, **k: 0.01)

    raw = {"SIPP": [{"ticker": "SCLX.L", "units": 73, "cost_basis_gbp": 500.0}]}
    builder = _fake_owner_builder(raw)
    _patch_route_sources(monkeypatch, "steve", raw, builder)
    monkeypatch.setattr("backend.common.portfolio.build_owner_portfolio", builder)

    app = create_app()
    client = _auth_client(app)
    instrument_resp = client.get("/instrument?ticker=SCLX.L&days=1&format=json")
    portfolio_resp = client.get("/portfolio/steve")

    assert instrument_resp.status_code == 200
    assert portfolio_resp.status_code == 200
    [pos] = instrument_resp.json()["positions"]
    [row] = [h for a in portfolio_resp.json()["accounts"] for h in a["holdings"]]

    # 1000 * 0.01 = 10.00/unit: scaled exactly once (not 1000 or 0.10).
    assert pos["current_price_gbp"] == pytest.approx(10.0)
    assert pos["market_value_gbp"] == pytest.approx(730.0)
    assert pos["gain_gbp"] == pytest.approx(230.0)
    assert pos["gain_pct"] == pytest.approx(46.0)
    assert pos["market_value_gbp"] == pytest.approx(row["market_value_gbp"])
    assert pos["gain_gbp"] == pytest.approx(row["gain_gbp"])
    assert pos["unrealised_gain_gbp"] == pytest.approx(row["unrealised_gain_gbp"])
    assert pos["gain_pct"] == pytest.approx(row["gain_pct"])
    assert pos["current_price_gbp"] == pytest.approx(row["current_price_gbp"])


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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "USD"}),
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
            return pd.DataFrame(
                {
                    "Datetime": [pd.Timestamp("2024-01-02T10:00:00")],
                    "Close": [10.0],
                }
            )

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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
        patch("backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df),
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json&base_currency=USD")
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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "USD"}),
        patch("backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df),
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.N&days=1&format=json&base_currency=EUR")
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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=df),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
        patch("backend.routes.instrument.get_security_meta", return_value={"currency": "GBP"}),
        patch("backend.routes.instrument.fetch_fx_rate_range", return_value=fx_df),
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
    with (
        patch("backend.routes.instrument.load_meta_timeseries_range", return_value=empty),
        patch("backend.routes.instrument.get_security_meta", return_value={}),
        patch("backend.routes.instrument.list_portfolios", return_value=[]),
    ):
        client = _auth_client(app)
        resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 404


def test_gbx_prices_scaled(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [100.0, 120.0],
        }
    )

    monkeypatch.setattr("backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df)
    monkeypatch.setattr("backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBX"})
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: [])

    client = _auth_client(app)
    resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    prices = resp.json()["prices"]
    assert prices[-1]["close"] == pytest.approx(120.0)
    assert prices[-1]["close_gbp"] == pytest.approx(1.2)


def test_gbx_close_gbp_not_double_scaled_by_pence_override(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [100.0, 120.0],
        }
    )

    monkeypatch.setattr("backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df)
    monkeypatch.setattr("backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBX"})
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: [])
    monkeypatch.setattr("backend.routes.instrument.get_scaling_override", lambda *_: 0.01)

    def _scale_close_only(df_in, scale):
        df_scaled = df_in.copy()
        df_scaled["Close"] = pd.to_numeric(df_scaled["Close"], errors="coerce") * scale
        return df_scaled

    monkeypatch.setattr("backend.routes.instrument.apply_scaling", _scale_close_only)

    client = _auth_client(app)
    resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["prices"][-1]["close"] == pytest.approx(1.2)
    assert payload["prices"][-1]["close_gbp"] == pytest.approx(1.2)


def test_gbx_close_gbp_tracks_scaled_close_for_non_pence_override(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2020-01-01", periods=2, freq="D"),
            "Close": [100.0, 120.0],
        }
    )

    monkeypatch.setattr("backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df)
    monkeypatch.setattr("backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBX"})
    monkeypatch.setattr("backend.routes.instrument.list_portfolios", lambda: [])
    monkeypatch.setattr("backend.routes.instrument.get_scaling_override", lambda *_: 0.001)

    def _scale_close_only(df_in, scale):
        df_scaled = df_in.copy()
        df_scaled["Close"] = pd.to_numeric(df_scaled["Close"], errors="coerce") * scale
        return df_scaled

    monkeypatch.setattr("backend.routes.instrument.apply_scaling", _scale_close_only)

    client = _auth_client(app)
    resp = client.get("/instrument?ticker=ABC.L&days=1&format=json")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["prices"][-1]["close"] == pytest.approx(0.12)
    assert payload["prices"][-1]["close_gbp"] == pytest.approx(0.0012)


def test_base_currency_fetch_failure_is_resilient(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()

    monkeypatch.setattr("backend.routes.instrument.load_meta_timeseries_range", lambda *args, **kwargs: df)
    monkeypatch.setattr("backend.routes.instrument.get_security_meta", lambda ticker: {"currency": "GBP"})
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
