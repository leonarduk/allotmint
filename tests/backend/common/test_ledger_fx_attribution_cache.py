"""Ledger FX attribution through the real cache-only loaders and route (#9804).

A real meta parquet and ``timeseries/fx/USD.parquet`` with rates on Mon/Wed/Fri
only, so the bounded gap fill is exercised. Any live price or FX fetch fails
the test (#8028).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.utils.fx_rates as fx_rates
import backend.utils.timeseries_helpers as helpers
from backend.app import create_app
from backend.common import ledger_performance as lp
from backend.common import portfolio_utils as pu
from backend.config import config
from backend.timeseries import cache


@pytest.fixture
def cached_usd(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Store USCO.N closes and USD rates; both currency resolvers say USD; live fetches explode."""

    def explode(*_args, **_kwargs):
        raise AssertionError("the FX attribution is cache-only and must not fetch")

    meta = {"currency": "USD"}
    monkeypatch.setattr(pu, "get_instrument_meta", lambda _t: dict(meta))
    monkeypatch.setattr(pu, "get_security_meta", lambda _t: dict(meta))
    monkeypatch.setattr(pu, "instrument_currency", lambda _t, _e: meta["currency"])
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: dict(meta))
    monkeypatch.setattr(helpers, "get_scaling_override", lambda *_args: 1.0)
    monkeypatch.setattr(lp, "_resolve_symbol", lambda key: tuple(key.split(".", 1)))
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", explode)
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", explode)
    monkeypatch.setattr(cache, "load_meta_timeseries", explode)  # the live price loader
    monkeypatch.setattr(cache.refresh_queue, "enqueue", lambda *_args: False)
    monkeypatch.setattr(cache.refresh_queue, "enqueue_fx", lambda *_args: False)

    def clear_lrus() -> None:
        cache._memoized_range_cached.cache_clear()
        cache._load_meta_parquet_cached.cache_clear()

    def store(days: list[date], closes: list[float], rates: dict[date, float]) -> None:
        clear_lrus()
        path = cache.meta_timeseries_cache_path("USCO", "N")
        cache._ensure_local_dir(path)
        frame = pd.DataFrame({"Date": pd.to_datetime(days), "Close": closes})
        frame.assign(Open=frame["Close"], High=frame["Close"], Low=frame["Close"], Volume=1000).to_parquet(
            path, index=False
        )
        fx_path = cache._fx_cache_path("USD")
        cache._ensure_local_dir(fx_path)
        pd.DataFrame({"Date": pd.to_datetime(list(rates)), "Rate": list(rates.values())}).to_parquet(
            fx_path, index=False
        )

    yield store
    clear_lrus()


def _history(days: list[date]) -> tuple[list[float], dict[date, float]]:
    closes = [100.0 + 0.7 * i for i in range(len(days))]
    # Rates on Mon/Wed/Fri only: Tue/Thu closes take the previous stored rate.
    rates = {day: 0.80 - 0.002 * i for i, day in enumerate(days) if day.weekday() in (0, 2, 4)}
    return closes, rates


def _ledger(first: date) -> lp.AccountLedger:
    return lp.AccountLedger(
        "isa",
        [
            {"date": first.isoformat(), "type": "DEPOSIT", "amount_minor": 1_000_000},
            {"date": first.isoformat(), "type": "BUY", "ticker": "USCO.N", "units": 50, "amount_minor": 400_000},
        ],
        True,
    )


def test_split_reconciles_with_close_gbp_from_the_cache_only_loader(cached_usd) -> None:
    """P x X follows the stored Close_gbp, so a window without trades has no residual."""
    days = list(pd.bdate_range("2024-03-01", "2024-03-28").date)
    closes, rates = _history(days)
    cached_usd(days, closes, rates)

    with cache.cache_only():
        perf = lp.build_ledger_performance([_ledger(days[0])], days[-1])
        assert perf is not None
        result = lp.fx_attribution(perf, days[0], days[-1])

    [row] = result["instruments"]
    assert row["quote_status"] == lp.QUOTE_FOREIGN
    assert row["residual_gbp"] == pytest.approx(0.0, abs=1e-6)
    assert row["unattributed_gbp"] == 0.0
    expected = lp.contributions(perf, days[0], days[-1])["pnl_gbp"]["USCO.N"]
    assert row["local_gbp"] + row["fx_gbp"] == pytest.approx(expected, abs=1e-6)
    assert row["local_gbp"] > 0 > row["fx_gbp"]
    assert result[pu.UNCONVERTED_HOLDINGS_KEY] == []


def test_fx_attribution_route_is_cache_only_and_reports_coverage(cached_usd, monkeypatch) -> None:
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    today = date.today()
    days = list(pd.bdate_range(today - timedelta(days=40), today - timedelta(days=1)).date)
    closes, rates = _history(days)
    cached_usd(days, closes, rates)
    monkeypatch.setattr(lp, "load_owner_ledgers", lambda _owner: [_ledger(days[0])])
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {
            "owner": owner,
            "accounts": [{"holdings": [{"ticker": "USCO.N", "units": 50}]}],
            "total_value_estimate_gbp": 12_000.0,
        },
    )

    resp = TestClient(create_app()).get("/performance/alice/fx-attribution?days=365")

    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "alice"
    attribution = body["fx_attribution"]
    [row] = attribution["instruments"]
    assert row["ticker"] == "USCO.N"
    totals = attribution["totals"]
    parts = sum(totals[c] for c in ("local_gbp", "fx_gbp", "income_gbp", "residual_gbp", "unattributed_gbp"))
    assert parts == pytest.approx(totals["pnl_gbp"], abs=0.01)
    assert [group["currency"] for group in attribution["by_currency"]] == ["USD"]
    coverage = attribution["coverage"]
    assert coverage["portfolio_value_gbp"] == 12_000.0
    assert coverage["share"] == pytest.approx(coverage["ledger_value_gbp"] / 12_000.0)
    assert coverage["unreconciled_holdings"] == []
    assert attribution["cash_fx_modelled"] is False


def test_fx_attribution_route_without_a_ledger_is_null(monkeypatch) -> None:
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(lp, "load_owner_ledgers", lambda _owner: [])
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, pricing_date=None: {"owner": owner, "accounts": [], "total_value_estimate_gbp": 0.0},
    )

    resp = TestClient(create_app()).get("/performance/alice/fx-attribution")

    assert resp.status_code == 200
    assert resp.json() == {"owner": "alice", "fx_attribution": None}


def test_fx_attribution_route_unknown_owner_is_404(monkeypatch) -> None:
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    def missing(owner, pricing_date=None):
        raise FileNotFoundError(owner)

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", missing)

    assert TestClient(create_app()).get("/performance/nobody/fx-attribution").status_code == 404
