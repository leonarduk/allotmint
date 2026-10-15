"""Ledger transactions restated onto the split-adjusted share basis (#10915).

CGT.L: bought 400 @ ~£50 in 2021, sold in 2025, then a 10-for-1 split on
2026-07-23. Yahoo's stored closes are back-adjusted for that split (~£5), so
without restating the units the position is valued at a tenth of its worth.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backend.common import ledger_performance as lp
from backend.common.split_restatement import restate_for_splits, split_factor_after

SPLITS = {"CGT.L": ((pd.Timestamp("2026-07-23"), 10.0),)}


def splits_for(ticker):
    return SPLITS.get(ticker, ())


def test_quantity_and_price_are_restated_for_a_later_split_and_cash_is_not():
    tx = {
        "date": "2021-08-02",
        "type": "BUY",
        "ticker": "CGT.L",
        "units": 400.0,
        "price_gbp": 50.0,
        "amount_minor": 2000000,
    }

    (out,) = restate_for_splits([tx], splits_for)

    assert out["units"] == pytest.approx(4000.0)
    assert out["price_gbp"] == pytest.approx(5.0)
    assert out["amount_minor"] == 2000000
    assert tx["units"] == 400.0  # input not mutated


@pytest.mark.parametrize("day", ["2026-07-23", "2026-08-01"])
def test_a_trade_on_or_after_the_split_is_already_on_the_new_basis(day):
    tx = {"date": day, "type": "BUY", "ticker": "CGT.L", "units": 4000.0}
    assert restate_for_splits([tx], splits_for) == [tx]


def test_consolidations_and_compounding():
    splits = ((pd.Timestamp("2022-07-18"), 0.8), (pd.Timestamp("2024-01-02"), 2.0))
    assert split_factor_after(splits, pd.Timestamp("2020-09-29")) == pytest.approx(1.6)
    assert split_factor_after(splits, pd.Timestamp("2023-01-01")) == pytest.approx(2.0)
    assert split_factor_after(splits, pd.Timestamp("2025-01-01")) == 1.0


def test_shares_field_is_scaled_and_rows_without_ticker_date_or_splits_pass_through():
    shares = {"date": "2021-01-04", "type": "BUY", "ticker": "CGT.L", "shares": 100_000_000}
    rows = [
        {"date": "2021-01-04", "type": "DEPOSIT", "amount_minor": 100},
        {"type": "BUY", "ticker": "CGT.L", "units": 1},
        {"date": "2021-01-04", "type": "BUY", "ticker": "AAA.L", "units": 1},
    ]

    restated = restate_for_splits([shares, *rows], splits_for)

    assert restated[0]["shares"] == pytest.approx(1_000_000_000)
    assert restated[1:] == rows


def test_ledger_values_a_pre_split_position_at_its_real_worth():
    closes = {"CGT.L": {"2025-04-08": 4.80, "2025-04-10": 4.79}}  # adjusted £ (≈ £48 pre-split)
    ledger = lp.AccountLedger(
        "isa",
        [
            {"date": "2025-04-08", "type": "DEPOSIT", "amount_minor": 1920000},
            {
                "date": "2025-04-08",
                "type": "BUY",
                "ticker": "CGT.L",
                "units": 400,
                "price_gbp": 48.0,
                "amount_minor": 1920000,
            },
            {
                "date": "2025-04-10",
                "type": "SELL",
                "ticker": "CGT.L",
                "units": 400,
                "price_gbp": 47.9,
                "amount_minor": 1916000,
            },
        ],
        True,
    )

    def loader(key, start, end):
        return pd.Series({pd.Timestamp(d): p for d, p in closes.get(key, {}).items()}, dtype=float)

    perf = lp.build_ledger_performance([ledger], date(2025, 4, 11), price_loader=loader, splits_for=splits_for)

    assert perf.units.loc[pd.Timestamp("2025-04-08"), "CGT.L"] == pytest.approx(4000.0)
    assert perf.instrument_values.loc[pd.Timestamp("2025-04-08"), "CGT.L"] == pytest.approx(19200.0)
    # No fake gain on the sale: the account ends at its cash, close to what went in.
    assert perf.values.iloc[-1] == pytest.approx(19160.0)
    assert perf.returns.abs().max() < 0.01


def test_unreconciled_flags_a_holding_left_on_the_pre_split_count():
    ledger = lp.AccountLedger("isa", [{"date": "2021-08-02", "type": "BUY", "ticker": "CGT.L", "units": 400}], False)

    stale = [{"ticker": "CGT.L", "units": 400}]
    current = [{"ticker": "CGT.L", "units": 4000}]

    assert lp.unreconciled_instruments([ledger], stale, splits_for=splits_for) == ("CGT.L",)
    assert lp.unreconciled_instruments([ledger], current, splits_for=splits_for) == ()
