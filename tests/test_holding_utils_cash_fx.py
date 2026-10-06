"""Cash held in a non-GBP account is valued at its GBP rate (#9754)."""

from datetime import date

import pytest

from backend.common import portfolio_utils
from backend.common.holding_utils import enrich_holding
from backend.utils.fx_rates import FX_RATE_SOURCE_CACHE, FX_RATE_SOURCE_MISSING


@pytest.fixture
def fx_rates(monkeypatch):
    """Serve ``fx_rate_to_gbp_with_source`` from a dict; record what was asked for."""
    rates: dict[str, float] = {}
    asked: list[str] = []

    def fake(currency):
        asked.append(currency)
        rate = rates.get(currency)
        return (rate, FX_RATE_SOURCE_CACHE) if rate is not None else (None, FX_RATE_SOURCE_MISSING)

    monkeypatch.setattr(portfolio_utils, "fx_rate_to_gbp_with_source", fake)
    return rates, asked


def _enrich(holding):
    return enrich_holding(holding, date.today(), {}, {})


def test_usd_account_cash_is_valued_at_the_gbp_rate(fx_rates):
    rates, _ = fx_rates
    rates["USD"] = 0.8

    out = _enrich({"ticker": "CASH.USD", "units": 1000, "currency": "USD", "cost_basis_gbp": 5.0})

    assert out["market_value_gbp"] == pytest.approx(800.0)
    assert out["current_price_gbp"] == 0.8
    # Cash cost is its value, whatever is stored (#7012).
    assert out["cost_basis_gbp"] == pytest.approx(800.0)
    assert out["effective_cost_basis_gbp"] == pytest.approx(800.0)
    assert out["gain_gbp"] == 0.0
    assert out["fx_rate_source"] == FX_RATE_SOURCE_CACHE


def test_cash_with_no_rate_is_left_unvalued_and_flagged(fx_rates):
    out = _enrich({"ticker": "CASH.USD", "units": 1000, "currency": "USD"})

    assert out["market_value_gbp"] is None
    assert out["current_price_gbp"] is None
    assert out["fx_rate_source"] == FX_RATE_SOURCE_MISSING


def test_pence_account_cash_is_gbp_without_fx(fx_rates):
    _, asked = fx_rates

    out = _enrich({"ticker": "CASH.GBX", "units": 500, "currency": "GBX"})

    assert out["market_value_gbp"] == pytest.approx(5.0)
    assert out["current_price_gbp"] == 0.01
    assert out["fx_rate_source"] is None
    assert asked == []


def test_gbp_cash_is_unchanged(fx_rates):
    _, asked = fx_rates

    out = _enrich({"ticker": "CASH.GBP", "units": 250.5, "cost_basis_gbp": 3.0})

    assert out["market_value_gbp"] == 250.5
    assert out["current_price_gbp"] == 1.0
    assert out["cost_basis_gbp"] == 250.5
    assert out["fx_rate_source"] is None
    assert asked == []
