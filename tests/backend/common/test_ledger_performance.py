"""Ledger-rebuilt time-weighted returns (backend.common.ledger_performance).

The fixture ledger is small enough to check by hand. One account, one GBP
instrument AAA.L (closes 100 on 29 Jan, 110 on 30 Jan, 99 from 12 Feb):

    Thu 29 Jan  deposit 1000, buy 10 @ 100      V = 1000            r = 0
    Fri 30 Jan  close 110                       V = 1100            r = +10%
    Wed 11 Feb  deposit 1100 (mid-month)        V = 2200, F = 1100  r = 0
    Thu 12 Feb  buy 10 @ 110, close 99          V = 1980            r = -10%
    Fri 13 Feb  dividend 30                     V = 2010            r = 2010/1980 - 1

    January  = +10%
    February = 0.9 * 2010/1980 - 1 = -8.636...%
    YTD      = 1.1 * 0.9 * 2010/1980 - 1 = 2010/2000 - 1 = +0.5%

Money in is 2100 and the account ends at 2010, so a naive value change reads
as a loss; the TWR must not count either deposit as return, and must count
the dividend as return.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from backend.common import ledger_performance as lp

END = date(2026, 2, 27)
CLOSES = {"AAA.L": {"2026-01-29": 100.0, "2026-01-30": 110.0, "2026-02-12": 99.0}}

TRANSACTIONS = [
    {"date": "2026-01-29", "type": "DEPOSIT", "amount_minor": 100000},
    {"date": "2026-01-29", "type": "BUY", "ticker": "AAA.L", "units": 10, "amount_minor": 100000},
    {"date": "2026-02-11", "type": "DEPOSIT", "amount_minor": 110000},
    {"date": "2026-02-12", "type": "BUY", "ticker": "AAA.L", "units": 10, "amount_minor": 110000},
    {"date": "2026-02-13", "type": "DIVIDEND", "amount_minor": 3000},
]

FEB_RETURN = 0.9 * 2010 / 1980 - 1


def fake_loader(closes=CLOSES):
    def load(key, start, end):
        points = closes.get(key, {})
        return pd.Series({pd.Timestamp(day): price for day, price in points.items()}, dtype=float)

    return load


def build(transactions=TRANSACTIONS, *, trade_cash=True, end=END, closes=CLOSES):
    ledger = lp.AccountLedger("isa", transactions, trade_cash)
    return lp.build_ledger_performance([ledger], end, price_loader=fake_loader(closes))


def test_values_follow_the_ledger_not_todays_holdings():
    perf = build()

    assert perf.inception == date(2026, 1, 29)
    assert perf.values[pd.Timestamp("2026-01-29")] == pytest.approx(1000.0)
    assert perf.values[pd.Timestamp("2026-02-11")] == pytest.approx(2200.0)
    assert perf.values[pd.Timestamp("2026-02-13")] == pytest.approx(2010.0)
    assert perf.values.iloc[-1] == pytest.approx(2010.0)


def test_mid_month_deposit_is_not_return():
    perf = build()

    assert perf.returns[pd.Timestamp("2026-02-11")] == pytest.approx(0.0)
    assert perf.returns[pd.Timestamp("2026-01-29")] == pytest.approx(0.0)


def test_dividend_counts_as_return():
    perf = build()

    assert perf.returns[pd.Timestamp("2026-02-13")] == pytest.approx(2010 / 1980 - 1)


def test_cash_interest_counts_as_return():
    # INTEREST shares the income path with DIVIDEND (#9169): return, not a flow.
    transactions = [*TRANSACTIONS[:-1], {"date": "2026-02-13", "type": "INTEREST", "amount_minor": 3000}]
    perf = build(transactions)

    assert perf.returns[pd.Timestamp("2026-02-13")] == pytest.approx(2010 / 1980 - 1)
    assert perf.flows[pd.Timestamp("2026-02-13")] == pytest.approx(0.0)


def test_monthly_and_ytd_chained_returns_match_hand_calculation():
    perf = build()

    assert lp.chained_return(perf.returns, date(2025, 12, 31), date(2026, 1, 31)) == pytest.approx(0.10)
    assert lp.chained_return(perf.returns, date(2026, 1, 31), END) == pytest.approx(FEB_RETURN)
    assert lp.chained_return(perf.returns, date(2025, 12, 31), END) == pytest.approx(0.005)
    # Since inception == YTD here, and a window entirely before inception is empty.
    assert lp.chained_return(perf.returns, None, END) == pytest.approx(0.005)
    assert lp.chained_return(perf.returns, None, date(2026, 1, 1)) is None


def test_ledger_without_trade_cash_gives_the_same_return():
    # No trade_cash_effects: cash is left out, buys are external flows and the
    # dividend is paid out as income -- the securities-plus-income return.
    perf = build(trade_cash=False)

    assert perf.values.iloc[-1] == pytest.approx(1980.0)
    assert lp.chained_return(perf.returns, None, END) == pytest.approx(0.005)


def test_transactions_after_end_are_ignored():
    perf = build(end=date(2026, 2, 10))

    assert perf.end == date(2026, 2, 10)
    assert perf.values.iloc[-1] == pytest.approx(1100.0)
    assert lp.chained_return(perf.returns, None, date(2026, 2, 10)) == pytest.approx(0.10)


def test_transfer_in_is_a_flow_at_market_value():
    transactions = [
        {"date": "2026-01-29", "type": "TRANSFER_IN", "ticker": "AAA.L", "units": 10, "amount_minor": 0},
    ]

    perf = build(transactions)

    assert perf.returns[pd.Timestamp("2026-01-29")] == pytest.approx(0.0)
    assert lp.chained_return(perf.returns, None, END) == pytest.approx(99 / 100 - 1)


def test_unpriced_instrument_is_valued_at_trade_price_and_flagged():
    perf = build(closes={})

    assert perf.unpriced == ("AAA.L",)
    # Valued at the last trade price, so it never jumps from zero.
    assert perf.values[pd.Timestamp("2026-01-30")] == pytest.approx(1000.0)
    assert perf.returns[pd.Timestamp("2026-01-29")] == pytest.approx(0.0)


def test_no_dated_transactions_returns_none():
    assert build([]) is None
    assert build([{"type": "DEPOSIT", "amount_minor": 100}]) is None


def test_contributions_and_weights():
    perf = build()

    frame = lp.contributions(perf, date(2026, 1, 31), END)
    # Feb P&L on AAA.L: 20 * 99 - (10 * 110 + 1100 bought) = -220.
    assert frame.loc["AAA.L", "pnl_gbp"] == pytest.approx(-220.0)
    assert frame.loc["AAA.L", "contribution"] == pytest.approx(-220.0 / 2200.0)
    weights, cash_weight = lp.weights_at(perf, END)
    assert weights == {"AAA.L": pytest.approx(1980 / 2010)}
    assert cash_weight == pytest.approx(30 / 2010)


def test_drawdown_uses_the_return_index():
    perf = build()

    dd = lp.drawdown(perf.returns, None, END)

    assert dd.peak == date(2026, 1, 30)
    assert dd.trough == date(2026, 2, 12)
    assert dd.max_drawdown == pytest.approx(-0.10)
    assert dd.current_drawdown == pytest.approx(0.9 * 2010 / 1980 - 1)
    assert dd.current_peak == date(2026, 1, 30)


def test_volatility_and_sharpe_need_enough_observations():
    returns = pd.Series([0.01, -0.01] * 15, index=pd.bdate_range("2026-01-01", periods=30))

    vol = lp.annualised_volatility(returns, None, date(2026, 3, 1))

    assert vol == pytest.approx(returns.std(ddof=1) * 252**0.5)
    assert lp.sharpe_ratio(returns, None, date(2026, 3, 1), 0.0) is not None
    assert lp.annualised_volatility(returns.head(5), None, date(2026, 3, 1)) is None


def test_annualise_only_after_a_year():
    assert lp.annualise(0.21, 730) == pytest.approx(1.21 ** (365.25 / 730) - 1)
    assert lp.annualise(0.05, 200) is None
    assert lp.annualise(None, 800) is None


def test_price_return_and_month_end_helpers():
    closes = pd.Series({pd.Timestamp("2026-01-30"): 100.0, pd.Timestamp("2026-02-27"): 105.0})

    assert lp.price_return(closes, date(2026, 1, 31), date(2026, 2, 28)) == pytest.approx(0.05)
    assert lp.price_return(closes, date(2025, 12, 31), date(2026, 2, 28)) is None
    assert lp.last_complete_month_end(date(2026, 10, 1)) == date(2026, 9, 30)
    assert lp.last_complete_month_end(date(2026, 9, 30)) == date(2026, 8, 31)
    assert lp.one_year_before(date(2028, 2, 29)) == date(2027, 2, 28)


def test_unreconciled_instruments_lists_holdings_the_ledger_cannot_reproduce():
    ledger = lp.AccountLedger("isa", TRANSACTIONS, True)
    holdings = [
        {"ticker": "AAA.L", "units": 20},
        {"ticker": "BBB.L", "units": 5},
        {"ticker": "CASH.GBP", "units": 30},
    ]

    assert lp.unreconciled_instruments([ledger], holdings) == ("BBB.L",)


def test_load_owner_ledgers_reads_the_accounts_root(tmp_path, monkeypatch):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "ISA_transactions.json").write_text(
        json.dumps({"trade_cash_effects": True, "transactions": TRANSACTIONS}), encoding="utf-8"
    )
    (owner_dir / "sipp_transactions.json").write_text(json.dumps({"transactions": []}), encoding="utf-8")
    (owner_dir / "broken_transactions.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(lp.config, "accounts_root", tmp_path)

    ledgers = lp.load_owner_ledgers("alice")

    assert [(ledger.account, ledger.trade_cash, len(ledger.transactions)) for ledger in ledgers] == [
        ("ISA", True, 5),
        ("sipp", False, 0),
    ]
    assert lp.load_owner_ledgers("nobody") == []
    assert lp.load_owner_ledgers("../alice") == []
