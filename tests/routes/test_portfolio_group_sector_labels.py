"""Route-level checks that the dashboard's data sources carry canonical labels (#8530).

The frontend never calls the /sectors or /regions aggregates for these views:

* /allocation (``AllocationCharts``) buckets ``accounts[].holdings[].sector``
  from ``GET /portfolio-group/{slug}``, i.e. ``enrich_holding`` output.
* The holdings table's Sector mode reads ``sector`` from
  ``GET /portfolio-group/{slug}/instruments`` (``aggregate_by_ticker`` rows)
  in rollup mode, falling back to the per-holding sector in flat mode.

So these tests drive the real ``build_group_portfolio`` -> ``enrich_holding``
path (only the portfolio source and owner-level side lookups are stubbed) and
assert both endpoints return the canonical labels.
"""

import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import group_portfolio, portfolio_loader
from backend.routes import portfolio
from backend.timeseries import cache as ts_cache

# The owner-portfolio module exactly as build_group_portfolio sees it.
owner_portfolio = group_portfolio.owner_portfolio

_FIXTURE_META = Path(__file__).resolve().parents[1] / "data" / "timeseries" / "meta"

_RAW_LABELS = {
    "Financial Services",
    "Technology",
    "Consumer Defensive",
    "Real Estate Investment Trusts",
    "UK",
}


@pytest.fixture(autouse=True)
def _offline_group(monkeypatch, tmp_path):
    """Serve prices from checked-in parquets and stub the portfolio source."""

    meta = tmp_path / "meta"
    meta.mkdir()
    for name in ("HFEL_L.parquet", "VWRL_L.parquet"):
        shutil.copy(_FIXTURE_META / name, meta / name)
    monkeypatch.setattr(ts_cache, "_CACHE_BASE", str(tmp_path))
    ts_cache._memoized_range_cached.cache_clear()
    ts_cache._load_meta_timeseries_cached.cache_clear()

    holdings = [
        {
            "ticker": "HFEL.L",
            "units": 10,
            "cost_basis_gbp": 20.0,
            "acquired_date": "2020-01-02",
            "sector": "Financial Services",
            "region": "UK",
        },
        {
            "ticker": "VWRL.L",
            "units": 5,
            "cost_basis_gbp": 300.0,
            "acquired_date": "2020-01-02",
            "sector": "Technology",
            "region": "GB",
        },
        {"ticker": "CASH.GBP", "units": 1000, "region": "United Kingdom"},
    ]
    portfolios = [{"owner": "alice", "accounts": [{"account_type": "ISA", "currency": "GBP", "holdings": holdings}]}]

    monkeypatch.setattr(
        group_portfolio,
        "list_groups",
        lambda: [{"slug": "demo", "name": "Demo", "members": ["alice"]}],
    )
    monkeypatch.setattr(portfolio_loader, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(group_portfolio, "load_approvals", lambda owner: {})
    monkeypatch.setattr(group_portfolio, "load_user_config", lambda owner: None)
    monkeypatch.setattr(owner_portfolio, "fill_missing_costs", lambda *args, **kwargs: None)
    monkeypatch.setattr(owner_portfolio, "load_trades", lambda owner: [])

    def _no_owner_portfolio(*args, **kwargs):
        raise FileNotFoundError("no owner portfolio in this test")

    monkeypatch.setattr(owner_portfolio, "build_owner_portfolio", _no_owner_portfolio)
    yield
    ts_cache._memoized_range_cached.cache_clear()
    ts_cache._load_meta_timeseries_cached.cache_clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(portfolio.router)
    return TestClient(app)


def test_group_portfolio_holdings_carry_canonical_labels():
    resp = _client().get("/portfolio-group/demo")
    assert resp.status_code == 200

    holdings = {h["ticker"]: h for acct in resp.json()["accounts"] for h in acct["holdings"]}

    assert holdings["HFEL.L"]["sector"] == "Financials"
    assert holdings["HFEL.L"]["region"] == "United Kingdom"
    assert holdings["VWRL.L"]["sector"] == "Information Technology"
    assert holdings["VWRL.L"]["region"] == "United Kingdom"
    assert holdings["CASH.GBP"]["sector"] == "Cash"
    assert holdings["CASH.GBP"]["region"] == "United Kingdom"
    for h in holdings.values():
        assert h["sector"] not in _RAW_LABELS
        assert h["region"] not in _RAW_LABELS


def test_group_instruments_rows_carry_canonical_labels():
    resp = _client().get("/portfolio-group/demo/instruments")
    assert resp.status_code == 200

    rows = {r["ticker"]: r for r in resp.json()}

    assert rows["HFEL.L"]["sector"] == "Financials"
    assert rows["HFEL.L"]["region"] == "United Kingdom"
    assert rows["VWRL.L"]["sector"] == "Information Technology"
    assert rows["VWRL.L"]["region"] == "United Kingdom"
    assert rows["CASH.GBP"]["sector"] == "Cash"
    assert rows["CASH.GBP"]["region"] == "United Kingdom"
    for r in rows.values():
        assert r["sector"] not in _RAW_LABELS
        assert r["region"] not in _RAW_LABELS


def test_group_sector_aggregate_agrees_with_rows():
    resp = _client().get("/portfolio-group/demo/sectors")
    assert resp.status_code == 200

    sectors = {row["sector"] for row in resp.json()}

    assert sectors == {"Financials", "Information Technology", "Cash"}
