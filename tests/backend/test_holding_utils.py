import datetime as dt

import pandas as pd
import pytest

from backend.common import holding_utils as hu
from backend.common.constants import ACQUIRED_DATE, COST_BASIS_GBP, TICKER, UNITS
from backend.common.holding_utils import EFFECTIVE_COST_BASIS_GBP


def test_enrich_holding_scales_booked_cost_basis(monkeypatch):
    """Booked GBX cost bases should respect scaling overrides."""

    # Always scale by 0.01 (e.g., GBX -> GBP)
    monkeypatch.setattr(hu, "get_scaling_override", lambda *args, **kwargs: 0.01)
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {})

    import backend.common.instrument_api as instrument_api
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {"FOO.L": {"last_price": 2.0, "is_stale": False}},
    )
    monkeypatch.setattr(hu, "_get_price_for_date_scaled", lambda *args, **kwargs: (1.9, "mock"))

    holding = {
        TICKER: "FOO.L",
        UNITS: 1,
        COST_BASIS_GBP: 123.45,
        ACQUIRED_DATE: "2024-01-01",
    }

    enriched = hu.enrich_holding(holding, dt.date(2024, 1, 31), price_cache={}, approvals=None, user_config=None)

    assert enriched[COST_BASIS_GBP] == pytest.approx(1.23)
    assert enriched[EFFECTIVE_COST_BASIS_GBP] == pytest.approx(1.23)
    assert enriched["gain_gbp"] == pytest.approx(0.77)


def test_gbx_scaling_defaults_apply_without_override(monkeypatch):
    import backend.common.holding_utils as hu
    import backend.common.instrument_api as instrument_api
    import backend.common.portfolio_utils as pu
    import backend.common.prices as prices
    from backend.utils import timeseries_helpers as tsh

    ticker = "FOO"
    exchange = "L"
    full_ticker = f"{ticker}.{exchange}"

    # Return GBX currency metadata for all lookups
    def _gbx_meta(*_args, **_kwargs):
        return {"currency": "GBX"}

    monkeypatch.setattr("backend.common.instruments.get_instrument_meta", _gbx_meta)
    monkeypatch.setattr(hu, "get_instrument_meta", _gbx_meta)
    monkeypatch.setattr(pu, "get_instrument_meta", _gbx_meta)
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {"currency": "GBX"})

    # Avoid live quote lookups and FX conversion noise
    monkeypatch.setattr(prices, "load_live_prices", lambda *_: {})
    monkeypatch.setattr(pu, "_fx_to_base", lambda *_: 1.0)

    # Simplify instrument API helpers
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda sym, *_args: (sym.split(".", 1)[0], exchange),
    )
    monkeypatch.setattr(instrument_api, "price_change_pct", lambda *_a, **_k: None)
    monkeypatch.setattr(instrument_api, "_resolve_grouping_details", lambda *_a, **_k: (None, None))

    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-29", "2024-01-30"]),
            "Open": [120.0, 124.0],
            "High": [125.0, 128.0],
            "Low": [119.0, 122.0],
            "Close": [123.0, 125.0],
            "Volume": [1000, 1200],
            "Ticker": [ticker, ticker],
            "Source": ["test", "test"],
        }
    )

    monkeypatch.setattr(hu, "load_meta_timeseries_range", lambda **_: frame.copy())
    monkeypatch.setattr(prices, "load_meta_timeseries_range", lambda *_a, **_k: frame.copy())

    # Fresh snapshot fixture for the aggregator to consume
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    # Scaling should be inferred from GBX metadata even without a JSON override
    assert tsh.get_scaling_override(ticker, exchange, None) == pytest.approx(0.01)

    latest = hu.load_latest_prices([full_ticker])
    assert latest[full_ticker] == pytest.approx(1.25)

    snapshot = prices.get_price_snapshot([full_ticker])
    assert snapshot[full_ticker]["last_price"] == pytest.approx(1.25)

    pu._PRICE_SNAPSHOT[full_ticker] = snapshot[full_ticker]

    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": full_ticker,
                        "units": 1,
                        "cost_gbp": 1.0,
                    }
                ]
            }
        ]
    }

    rows = pu.aggregate_by_ticker(portfolio)
    row = next(r for r in rows if r["ticker"] == full_ticker)
    assert row["last_price_gbp"] == pytest.approx(1.25)
    assert row["market_value_gbp"] == pytest.approx(1.25)
    assert row["gain_gbp"] == pytest.approx(0.25)


def test_enrich_holding_market_value_set_from_price_snapshot(monkeypatch):
    """market_value_gbp must not be None when a price exists in the snapshot.

    Root cause of issue #2746: holdings with zero cost-basis and no timeseries
    cache got market_value_gbp=None because the price snapshot was empty on
    first start.  The seed data/prices/latest_prices.json fixes the snapshot;
    this test guards the enrichment path.
    """
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(
        hu,
        "get_instrument_meta",
        lambda *_: {"name": "Vanguard FTSE All-World", "currency": "GBP"},
    )
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {"VWRL.L": {"last_price": 97.5, "price_currency": "GBP", "is_stale": False}},
    )
    # Stub out timeseries access — only the snapshot price should be used.
    monkeypatch.setattr(hu, "_get_price_for_date_scaled", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)

    holding = {TICKER: "VWRL.L", UNITS: 10, COST_BASIS_GBP: 0.0, ACQUIRED_DATE: "2025-01-01"}
    today = dt.date(2026, 5, 16)
    result = hu.enrich_holding(holding, today, price_cache={})

    assert result["market_value_gbp"] == pytest.approx(
        975.0
    ), "market_value_gbp must not be None when price snapshot has data"
    assert result["gain_gbp"] is not None
    assert result["current_price_gbp"] == pytest.approx(97.5)


def test_enrich_holding_falls_back_to_previous_close_when_today_missing(monkeypatch):
    """If today's close is unavailable (e.g. a gap in the price source, or a
    NaN-filled placeholder row for a date outside the cache), the holding must
    fall back to the last known close rather than leaving price fields null.
    """
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {"currency": "GBP"})
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    def fake_price_for_date(ticker, exchange, d, field="Close_gbp"):
        # No price for "today"; a valid close exists for the previous date.
        if d == dt.date(2026, 5, 15):
            return 50.0, "Yahoo"
        return None, None

    monkeypatch.setattr(hu, "_get_price_for_date_scaled", fake_price_for_date)
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)

    holding = {TICKER: "FOO.L", UNITS: 10, COST_BASIS_GBP: 0.0, ACQUIRED_DATE: "2025-01-01"}
    today = dt.date(2026, 5, 16)
    result = hu.enrich_holding(holding, today, price_cache={})

    assert result["price"] == pytest.approx(50.0)
    assert result["current_price_gbp"] == pytest.approx(50.0)
    assert result["market_value_gbp"] == pytest.approx(500.0)


def test_enrich_holding_monday_fallback_reaches_previous_friday(monkeypatch):
    """Regression for issue #5208: when pricing_date lands on a Monday and
    Monday's own close is missing, the fallback must reach back to the
    previous Friday's close rather than Sunday (a non-trading day). Uses
    PricingDateCalculator.previous_pricing_date (already weekend-aware via
    _nearest_weekday), not a naive pricing_date - timedelta(days=1)."""
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {"currency": "GBP"})
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})

    previous_friday = dt.date(2026, 5, 15)

    def fake_price_for_date(ticker, exchange, d, field="Close_gbp"):
        # Monday's close is missing; only the previous Friday has a price.
        if d == previous_friday:
            return 42.0, "Yahoo"
        return None, None

    monkeypatch.setattr(hu, "_get_price_for_date_scaled", fake_price_for_date)
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)

    holding = {TICKER: "FOO.L", UNITS: 10, COST_BASIS_GBP: 0.0, ACQUIRED_DATE: "2025-01-01"}
    # today = Tuesday so calc.reporting_date resolves to the preceding Monday.
    today = dt.date(2026, 5, 19)
    result = hu.enrich_holding(holding, today, price_cache={})

    assert result["price"] == pytest.approx(42.0)
    assert result["current_price_gbp"] == pytest.approx(42.0)
    assert result["market_value_gbp"] == pytest.approx(420.0)
    assert result["is_stale"] is True


def test_enrich_holding_no_acquired_date_stays_null(monkeypatch):
    """Regression for #7220: a holding with no real transaction/lot date must
    not have its acquired_date fabricated from the price-history start date
    (today - 365 days). The field, days_held, eligible_on, and
    next_eligible_sell_date must stay genuinely null, and sell_eligible must
    be null (unknown) rather than a confident False, so the frontend can
    render an explicit "unknown" state instead of a fake verdict.
    """
    import backend.common.instrument_api as instrument_api
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {})
    monkeypatch.setattr(hu, "_get_price_for_date_scaled", lambda *a, **k: (1.0, "mock"))
    monkeypatch.setattr(hu, "get_effective_cost_basis_gbp", lambda h, cache, price_hint=None: 0.0)

    holding = {TICKER: "FOO.L", UNITS: 1, COST_BASIS_GBP: 0.0}
    today = dt.date(2026, 8, 27)

    out = hu.enrich_holding(holding, today, price_cache={}, approvals={})

    assert out[ACQUIRED_DATE] is None
    assert out["days_held"] is None
    assert out["eligible_on"] is None
    assert out["next_eligible_sell_date"] is None
    assert out["days_until_eligible"] is None
    assert out["sell_eligible"] is None


def test_get_effective_cost_basis_gbp_falls_back_to_price_hint_when_unknown(monkeypatch):
    """Direct unit test for the price_hint fallback added alongside #7220.

    No booked cost_basis_gbp, no acquired_date, and an empty price_cache: the
    only value left to derive a cost from is the current price (price_hint).
    Exercises get_effective_cost_basis_gbp() itself -- not through
    enrich_holding() with the helper monkeypatched away -- so the actual
    fallback line is what's under test, not a stand-in.

    This path moves real portfolios' reported gain/gain% toward 0 (cost is
    set equal to market value) wherever a holding has neither a booked cost
    nor an acquisition date; see the #7220 review follow-up for measured
    real-data impact. get_effective_cost_basis_gbp() must also tag
    h["cost_basis_source"] = "unknown" in this branch (distinct from a real
    historical "derived" price) so callers/UI can tell a guess from a fact.
    """
    import backend.common.instrument_api as instrument_api

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(hu, "get_scaling_override", lambda *args, **kwargs: None)

    holding = {TICKER: "FOO.L", UNITS: 5}  # no COST_BASIS_GBP, no ACQUIRED_DATE

    result = hu.get_effective_cost_basis_gbp(holding, price_cache={}, price_hint=8.0)

    assert result == pytest.approx(40.0)  # 5 units * 8.0 price_hint
    assert holding["cost_basis_source"] == "unknown"


def test_get_effective_cost_basis_gbp_returns_zero_with_no_price_hint_either(monkeypatch):
    """No booked cost, no acquired date, empty cache, and no price_hint at
    all: there is truly nothing to derive a cost from, so this still returns
    0.0 (existing behaviour) rather than raising, and does not fabricate a
    cost_basis_source tag since no fallback value was actually produced.
    """
    import backend.common.instrument_api as instrument_api

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(hu, "get_scaling_override", lambda *args, **kwargs: None)

    holding = {TICKER: "FOO.L", UNITS: 5}

    result = hu.get_effective_cost_basis_gbp(holding, price_cache={}, price_hint=None)

    assert result == 0.0
    assert "cost_basis_source" not in holding


def test_enrich_holding_no_acquired_date_tags_cost_basis_source_unknown(monkeypatch):
    """End-to-end regression for the #7220 review follow-up: when
    enrich_holding() actually runs the real get_effective_cost_basis_gbp()
    (not a monkeypatched stand-in returning 0.0), a holding with no booked
    cost and no acquired date must report cost_basis_source == "unknown"
    rather than the generic "derived" a real historical derivation gets, and
    gain_gbp/gain_pct must reflect the resulting break-even (0.0), not a
    fabricated large gain and not a crash.
    """
    import backend.common.instrument_api as instrument_api
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {})
    monkeypatch.setattr(hu, "get_scaling_override", lambda *args, **kwargs: None)
    monkeypatch.setattr(hu, "_get_price_for_date_scaled", lambda *a, **k: (8.0, "mock"))

    holding = {TICKER: "FOO.L", UNITS: 5}  # no cost_basis_gbp, no acquired_date
    today = dt.date(2026, 8, 27)

    out = hu.enrich_holding(holding, today, price_cache={}, approvals={})

    assert out[ACQUIRED_DATE] is None
    assert out[EFFECTIVE_COST_BASIS_GBP] == pytest.approx(40.0)
    assert out["market_value_gbp"] == pytest.approx(40.0)
    assert out["gain_gbp"] == pytest.approx(0.0)
    assert out["gain_pct"] == pytest.approx(0.0)
    assert out["cost_basis_source"] == "unknown"
