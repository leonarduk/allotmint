"""``sell_block_reason`` tells the hold period apart from a pending approval (#10812)."""

from datetime import date, timedelta

import pytest

from backend.common.holding_utils import enrich_holding
from backend.common.user_config import UserConfig

TODAY = date(2026, 10, 13)  # a Tuesday
HOLD_DAYS = 30


def _cfg(exempt_types=None, exempt_tickers=None):
    return UserConfig(
        hold_days_min=HOLD_DAYS,
        approval_exempt_types=exempt_types or [],
        approval_exempt_tickers=exempt_tickers or [],
    )


def _holding(days_held: int | None, units: float = 1) -> dict:
    acquired = None if days_held is None else (TODAY - timedelta(days=days_held)).isoformat()
    return {"ticker": "BP.L", "acquired_date": acquired, "units": units, "cost_basis_gbp": 1.0}


@pytest.fixture(autouse=True)
def _stub_prices(monkeypatch):
    monkeypatch.setattr(
        "backend.common.holding_utils._get_dated_price_for_date_scaled",
        lambda *a, **k: (1.0, None, None),
    )
    monkeypatch.setattr(
        "backend.common.holding_utils._get_price_for_date_scaled",
        lambda *a, **k: (1.0, None),
    )


def test_past_hold_awaiting_approval_is_needs_approval():
    out = enrich_holding(_holding(524), TODAY, {}, {}, _cfg())
    assert out["sell_eligible"] is False
    assert out["days_until_eligible"] is None
    assert out["sell_block_reason"] == "needs_approval"


def test_inside_hold_period_is_hold_period_even_when_approval_needed():
    out = enrich_holding(_holding(6), TODAY, {}, {}, _cfg())
    assert out["sell_eligible"] is False
    assert out["days_until_eligible"] > 0
    assert out["sell_block_reason"] == "hold_period"


def test_inside_hold_period_with_approval_is_still_hold_period():
    out = enrich_holding(_holding(6), TODAY, {}, {"BP.L": TODAY}, _cfg())
    assert out["sell_eligible"] is False
    assert out["sell_block_reason"] == "hold_period"


def test_approved_past_hold_has_no_block_reason():
    out = enrich_holding(_holding(524), TODAY, {}, {"BP.L": TODAY}, _cfg())
    assert out["sell_eligible"] is True
    assert out["sell_block_reason"] is None


def test_exempt_past_hold_has_no_block_reason():
    out = enrich_holding(_holding(524), TODAY, {}, {}, _cfg(exempt_tickers=["BP.L"]))
    assert out["sell_eligible"] is True
    assert out["sell_block_reason"] is None


def test_unknown_acquisition_date_has_no_block_reason():
    out = enrich_holding(_holding(None), TODAY, {}, {}, _cfg())
    assert out["sell_eligible"] is None
    assert out["sell_block_reason"] is None


def test_cash_has_no_block_reason():
    out = enrich_holding({"ticker": "CASH.GBP", "units": 100, "currency": "GBP"}, TODAY, {}, {}, _cfg())
    assert out["sell_eligible"] is True
    assert out["sell_block_reason"] is None
