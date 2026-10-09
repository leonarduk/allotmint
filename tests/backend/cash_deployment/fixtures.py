"""Synthetic fixtures for the cash deployment tests (#10480). No real balances."""

from __future__ import annotations

from backend.common.investment_plan import InvestmentPlan


def synthetic_portfolio() -> dict:
    return {
        "accounts": [
            {
                "account_type": "ISA",
                "_account_stem": "isa",
                "holdings": [
                    {"ticker": "CASH.GBP", "market_value_gbp": 6000.0, "instrument_type": "Cash"},
                    {"ticker": "EQA.L", "market_value_gbp": 3000.0, "asset_class": "equity"},
                    {
                        "ticker": "GLT.L",
                        "market_value_gbp": 1000.0,
                        "asset_class": "bond",
                        "sub_asset_class": "long_gilts",
                    },
                ],
            },
            {
                "account_type": "SIPP",
                "_account_stem": "sipp",
                "holdings": [{"ticker": "EQB.L", "market_value_gbp": 2000.0, "asset_class": "equity"}],
            },
        ]
    }


def synthetic_plan() -> InvestmentPlan:
    return InvestmentPlan.model_validate(
        {
            "owner": "alex",
            "updated": "2026-01-01",
            "status": "active",
            "target": [
                {"class": "equity", "weight_pct": 60},
                {"class": "long_gilts", "weight_pct": 30},
                {"class": "cash", "weight_pct": 10},
            ],
            "vehicles": {"equity": ["VWX.L", "OTHER.L"], "long_gilts": [{"note": "a long gilt fund"}]},
        }
    )
