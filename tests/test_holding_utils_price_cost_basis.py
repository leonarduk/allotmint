import datetime as dt

import pandas as pd

from backend.common import holding_utils
from backend.common.constants import (
    ACQUIRED_DATE,
    COST_BASIS_GBP,
    TICKER,
    UNITS,
)


def test_get_price_for_date_scaled_cash():
    d = dt.date(2024, 1, 1)
    price, src = holding_utils._get_price_for_date_scaled("CASH", "L", d)
    assert price == 1.0
    assert src is None


def test_get_price_for_date_scaled_empty_data(monkeypatch):
    def fake_loader(*args, **kwargs):
        return pd.DataFrame()

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    d = dt.date(2024, 1, 1)
    price, src = holding_utils._get_price_for_date_scaled("AAA", "L", d)
    assert price is None
    assert src is None


def test_get_effective_cost_basis_gbp_booked_cost():
    holding = {TICKER: "AAA.L", UNITS: 10, COST_BASIS_GBP: 123.45}
    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 123.45


def test_get_effective_cost_basis_gbp_updates_booked_cost_when_scaled(monkeypatch):
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 0.5)

    holding = {TICKER: "ABC.L", UNITS: 10, COST_BASIS_GBP: 123.45}

    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 61.73
    assert holding[COST_BASIS_GBP] == 61.73


def test_get_effective_cost_basis_gbp_derived(monkeypatch):
    def fake_derived(ticker, exchange, acq, cache):
        return 2.0

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", fake_derived)
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    holding = {TICKER: "BBB.L", UNITS: 10, ACQUIRED_DATE: "2024-01-01"}
    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 20.0


def test_get_effective_cost_basis_gbp_cache_fallback(monkeypatch):
    def fake_derived(ticker, exchange, acq, cache):
        return None

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", fake_derived)
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    price_cache = {"CCC.L": 5.0}
    holding = {TICKER: "CCC.L", UNITS: 3, ACQUIRED_DATE: "2024-01-01"}
    assert holding_utils.get_effective_cost_basis_gbp(holding, price_cache) == 15.0
