import datetime as dt

import pandas as pd
import pytest

from backend.common.constants import ACQUIRED_DATE, COST_BASIS_GBP, TICKER, UNITS
from backend.common import holding_utils as hu
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
    monkeypatch.setattr(
        instrument_api, "_resolve_grouping_details", lambda *_a, **_k: (None, None)
    )

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

    assert result["market_value_gbp"] == pytest.approx(975.0), (
        "market_value_gbp must not be None when price snapshot has data"
    )
    assert result["gain_gbp"] is not None
    assert result["current_price_gbp"] == pytest.approx(97.5)
