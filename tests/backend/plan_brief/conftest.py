"""Shared fixtures for the plan-drift brief tests (#10475)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.common.investment_plan import InvestmentPlan

TODAY = date(2026, 10, 9)

PLAN_DATA = {
    "owner": "alex",
    "updated": "2026-01-10",
    "status": "active",
    "summary": "60/40 equity and long gilts",
    "target": [{"class": "equity", "weight_pct": 60}, {"class": "long_gilts", "weight_pct": 40}],
    "assumptions": [{"key": "bank_rate_pct", "value": 4.0}],
    "evidence": [
        {"as_of": "2025-11-01", "metric": "gilt_20y_yield", "value": 4.9, "source": "BoE"},
        {"as_of": "2026-09-01", "metric": "cpi", "value": 3.1},
    ],
    "open_questions": ["Add index-linked gilts?"],
    "review": {"next_review": "2026-10-01", "triggers": ["Bank Rate below 3%"]},
}


def holding(ticker, value, asset_class, sub=None, units=100.0, instrument_type=None):
    row = {"ticker": ticker, "market_value_gbp": value, "asset_class": asset_class, "units": units}
    if sub:
        row["sub_asset_class"] = sub
    if instrument_type:
        row["instrument_type"] = instrument_type
    return row


def portfolio(equity=66_000.0, gilts=30_000.0, cash=4_000.0):
    """Equity 66% vs a 60% target: +6.0pp, £6,000 over, on a £100,000 total."""
    return {
        "owner": "alex",
        "accounts": [
            {
                "_account_stem": "isa",
                "account_type": "ISA",
                "holdings": [
                    holding("VWRL.L", equity, "equity"),
                    holding("GLTL.L", gilts, "bond", sub="long_gilts"),
                    holding("CASH.GBP", cash, "cash", units=cash, instrument_type="cash"),
                ],
            }
        ],
    }


@pytest.fixture()
def plan() -> InvestmentPlan:
    return InvestmentPlan.model_validate(PLAN_DATA)
