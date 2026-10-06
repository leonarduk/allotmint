"""Local vs FX attribution of the ledger P&L (#9804).

``ledger_performance.fx_attribution`` decomposes each instrument's daily
``instrument_pnl`` on opening units into local, FX, income, residual and
unattributed. The core property: over any window the five parts add up to
``contributions().pnl_gbp`` for every instrument.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.common import ledger_performance as lp
from backend.common import portfolio_utils as pu

DAYS = pd.bdate_range("2026-01-02", "2026-01-30")
END = DAYS[-1].date()

# USD instrument: native close and GBP-per-USD rate both drift every day.
USD_NATIVE = pd.Series(100.0 + np.arange(len(DAYS)) * 1.5, index=DAYS)
USD_RATES = pd.Series(0.80 - np.arange(len(DAYS)) * 0.003, index=DAYS)
# No stored rate within the fill window on these days.
FX_GAP = [pd.Timestamp("2026-01-12"), pd.Timestamp("2026-01-13")]
GBP_CLOSES = pd.Series(50.0 + np.arange(len(DAYS)) * 0.5, index=DAYS)
# Only priced from 15 Jan: earlier days are valued at its trade price.
LATE_CLOSES = pd.Series(12.0, index=DAYS[DAYS >= pd.Timestamp("2026-01-15")])

TRANSACTIONS = [
    {"date": "2026-01-02", "type": "DEPOSIT", "amount_minor": 1_000_000},
    {"date": "2026-01-02", "type": "BUY", "ticker": "USCO.N", "units": 10, "amount_minor": 90_000},
    {"date": "2026-01-02", "type": "BUY", "ticker": "AAA.L", "units": 20, "amount_minor": 100_000},
    {"date": "2026-01-05", "type": "BUY", "ticker": "LATE.L", "units": 100, "amount_minor": 100_000},
    {"date": "2026-01-09", "type": "SELL", "ticker": "USCO.N", "units": 4, "amount_minor": 40_000},
    {"date": "2026-01-14", "type": "TRANSFER_IN", "ticker": "USCO.N", "units": 3, "amount_minor": 0},
    {"date": "2026-01-16", "type": "DIVIDEND", "ticker": "USCO.N", "amount_minor": 2_500},
    {"date": "2026-01-21", "type": "BUY", "ticker": "AAA.L", "units": 5, "amount_minor": 30_000},
]

QUOTES = {
    "USCO.N": lp.NativeQuote("USCO", "N", "USD", "USD", USD_NATIVE),
    "AAA.L": lp.NativeQuote("AAA", "L", "GBP", "GBP"),
    "LATE.L": lp.NativeQuote("LATE", "L", "GBP", "GBP"),
}


def rates_with_gap(currency: str, dates: pd.Index) -> pd.Series:
    assert currency == "USD"
    rates = USD_RATES.reindex(pd.DatetimeIndex(dates))
    rates[rates.index.isin(FX_GAP)] = float("nan")
    return pd.Series(rates.to_numpy(), index=dates)


def gbp_loader(key: str, start: date, end: date) -> pd.Series:
    """What ``load_gbp_closes`` returns: native x rate, dates without a rate left out."""
    if key == "USCO.N":
        return (USD_NATIVE * rates_with_gap("USD", USD_NATIVE.index)).dropna()
    return {"AAA.L": GBP_CLOSES, "LATE.L": LATE_CLOSES}[key]


def build(transactions=TRANSACTIONS) -> lp.LedgerPerformance:
    perf = lp.build_ledger_performance([lp.AccountLedger("isa", transactions, True)], END, price_loader=gbp_loader)
    assert perf is not None
    return perf


def attribute(perf, after, through=END, quotes=QUOTES, rates=rates_with_gap):
    return lp.fx_attribution(perf, after, through, quote_loader=lambda key, *_: quotes.get(key), rate_loader=rates)


def parts(row) -> float:
    return sum(row[c] for c in ("local_gbp", "fx_gbp", "income_gbp", "residual_gbp", "unattributed_gbp"))


WINDOWS = [
    (None, END),
    (date(2026, 1, 1), END),
    (date(2026, 1, 6), date(2026, 1, 20)),
    (date(2026, 1, 9), date(2026, 1, 14)),  # sell, FX gap and transfer
    (date(2026, 1, 13), date(2026, 1, 16)),  # last gap day, transfer, dividend
    (date(2026, 1, 20), END),
    (date(2026, 1, 30), END),  # empty window
]


@pytest.mark.parametrize(("after", "through"), WINDOWS)
def test_components_add_up_to_contributions_for_every_instrument_and_window(after, through) -> None:
    perf = build()

    result = attribute(perf, after, through)

    expected = lp.contributions(perf, after, through)["pnl_gbp"]
    rows = {row["key"]: row for row in result["instruments"]}
    for key, pnl in expected.items():
        if abs(pnl) < 1e-9 and key not in rows:
            continue
        assert rows[key]["pnl_gbp"] == pytest.approx(pnl, abs=0.01)
        assert parts(rows[key]) == pytest.approx(pnl, abs=0.01)
    assert result["totals"]["pnl_gbp"] == pytest.approx(float(expected.sum()), abs=0.01)
    assert parts(result["totals"]) == pytest.approx(result["totals"]["pnl_gbp"], abs=0.01)
    by_currency_pnl = sum(group["pnl_gbp"] for group in result["by_currency"])
    assert by_currency_pnl == pytest.approx(result["totals"]["pnl_gbp"], abs=0.01)


@pytest.mark.parametrize(
    ("after", "through"),
    [
        (date(2026, 1, 9), date(2026, 1, 20)),  # FX gap, a transfer at the close and a dividend
        (date(2026, 1, 21), END),
    ],
)
def test_residual_is_zero_without_trades(after, through) -> None:
    """The split is not a plug: with no buys or sells in the window, nothing is left over."""
    result = attribute(build(), after, through)

    for row in result["instruments"]:
        assert row["residual_gbp"] == pytest.approx(0.0, abs=1e-9), row["key"]
    assert result["totals"]["local_gbp"] != 0.0 and result["totals"]["fx_gbp"] != 0.0


def test_trades_land_in_residual_not_in_local_or_fx() -> None:
    """Bought at 90/unit (USD 100 x 0.80 = 80 at the close): the 10/unit gap is trade timing."""
    perf = build()

    usd = next(row for row in attribute(perf, None)["instruments"] if row["key"] == "USCO.N")
    first_day = next(row for row in attribute(perf, None, date(2026, 1, 2))["instruments"] if row["key"] == "USCO.N")

    assert first_day["local_gbp"] == 0.0 and first_day["fx_gbp"] == 0.0
    assert first_day["residual_gbp"] == pytest.approx(10 * 80.0 - 900.0)
    assert usd["income_gbp"] == pytest.approx(25.0)


def test_usd_holding_up_ten_percent_with_usd_down_five_percent() -> None:
    """Constant units, native 100 -> 110 and 0.80 -> 0.76 GBP/USD in one day."""
    days = pd.bdate_range("2026-03-02", "2026-03-04")
    native = pd.Series([100.0, 100.0, 110.0], index=days)
    rates = pd.Series([0.80, 0.80, 0.76], index=days)
    quotes = {"USCO.N": lp.NativeQuote("USCO", "N", "USD", "USD", native)}
    ledger = lp.AccountLedger(
        "isa",
        [
            {"date": "2026-03-02", "type": "DEPOSIT", "amount_minor": 800_000},
            {"date": "2026-03-02", "type": "BUY", "ticker": "USCO.N", "units": 100, "amount_minor": 800_000},
        ],
        True,
    )
    perf = lp.build_ledger_performance([ledger], days[-1].date(), price_loader=lambda *_: native * rates)
    assert perf is not None

    result = attribute(perf, days[0].date(), days[-1].date(), quotes, lambda _c, dates: rates.reindex(dates))

    row = result["instruments"][0]
    # 8000 GBP of USD stock: +10% local is +800; FX -5% of the 8800 it became is -440.
    assert row["local_gbp"] == pytest.approx(800.0)
    assert row["fx_gbp"] == pytest.approx(-440.0)
    assert row["residual_gbp"] == pytest.approx(0.0, abs=1e-9)
    assert row["unattributed_gbp"] == 0.0
    assert row["pnl_gbp"] == pytest.approx(100 * (110 * 0.76 - 100 * 0.80))
    assert result["by_currency"] == [
        {
            "currency": "USD",
            "fx_applicable": True,
            "local_gbp": pytest.approx(800.0),
            "fx_gbp": pytest.approx(-440.0),
            "income_gbp": 0.0,
            "residual_gbp": pytest.approx(0.0, abs=1e-9),
            "unattributed_gbp": 0.0,
            "pnl_gbp": pytest.approx(360.0),
        }
    ]


def test_sterling_holdings_have_no_fx_component_and_are_flagged_not_applicable() -> None:
    perf = build()

    result = attribute(perf, date(2026, 1, 1))

    aaa = next(row for row in result["instruments"] if row["key"] == "AAA.L")
    assert aaa["currency"] == "GBP"
    assert aaa["quote_status"] == lp.QUOTE_STERLING
    assert aaa["fx_applicable"] is False
    assert aaa["fx_gbp"] == 0.0
    assert aaa["local_gbp"] > 0
    gbp = next(group for group in result["by_currency"] if group["currency"] == "GBP")
    assert gbp["fx_applicable"] is False
    assert gbp["fx_gbp"] == 0.0


def test_fx_gap_days_are_unattributed_and_reported_as_unconverted() -> None:
    perf = build()

    result = attribute(perf, None)

    usd = next(row for row in result["instruments"] if row["key"] == "USCO.N")
    assert lp.UNATTRIBUTED_MISSING_FX in usd["unattributed_reasons"]
    # 12 Jan (no rate that day) and 13 Jan (none either), 14 Jan (no opening rate).
    assert usd["unattributed_days"] == 3
    assert usd["unattributed_gbp"] != 0.0
    [entry] = result[pu.UNCONVERTED_HOLDINGS_KEY]
    assert (entry["ticker"], entry["currency"], entry["reason"]) == ("USCO.N", "USD", pu.FX_MISSING_SOME_DATES)
    assert (entry["first"], entry["last"], entry["missing_fx_days"]) == ("2026-01-12", "2026-01-14", 3)


def test_window_without_fx_gaps_reports_nothing_unconverted() -> None:
    result = attribute(build(), date(2026, 1, 20))

    assert result[pu.UNCONVERTED_HOLDINGS_KEY] == []
    usd = next(row for row in result["instruments"] if row["key"] == "USCO.N")
    assert usd["unattributed_gbp"] == 0.0
    assert usd["unattributed_reasons"] == []


def test_trade_implied_price_days_are_unattributed() -> None:
    """LATE.L has no close before 15 Jan; the jump onto its first close is not a local return."""
    result = attribute(build(), None)

    late = next(row for row in result["instruments"] if row["key"] == "LATE.L")
    assert late["unattributed_reasons"] == [lp.UNATTRIBUTED_NO_MARKET_PRICE]
    assert late["unattributed_gbp"] == pytest.approx(100 * (12.0 - 10.0))
    assert late["local_gbp"] == 0.0
    assert parts(late) == pytest.approx(late["pnl_gbp"], abs=0.01)


@pytest.mark.parametrize(
    ("quote", "status"),
    [
        (lp.NativeQuote("USCO", "N", "EUR", "USD", USD_NATIVE), lp.QUOTE_MISMATCH),
        (lp.NativeQuote("USCO", "N", "USD", "GBP"), lp.QUOTE_MISMATCH),
        (lp.NativeQuote("USCO", "N", pu.UNKNOWN_CURRENCY_LABEL, "GBP"), lp.QUOTE_UNKNOWN),
    ],
)
def test_ambiguous_currency_is_not_split(quote, status) -> None:
    """The two resolvers disagree (#9798's ``currency_mismatch``) or know no currency: nothing is split."""
    result = attribute(build(), None, quotes={**QUOTES, "USCO.N": quote})

    usd = next(row for row in result["instruments"] if row["key"] == "USCO.N")
    assert usd["quote_status"] == status
    assert usd["unattributed_reasons"] == [status]
    assert usd["local_gbp"] == 0.0 and usd["fx_gbp"] == 0.0
    assert parts(usd) == pytest.approx(usd["pnl_gbp"], abs=0.01)


def test_unresolved_instrument_is_unattributed_at_trade_prices() -> None:
    result = attribute(build(), None, quotes={**QUOTES, "LATE.L": None})

    late = next(row for row in result["instruments"] if row["key"] == "LATE.L")
    assert late["quote_status"] == lp.QUOTE_UNRESOLVED
    assert late["currency"] == pu.UNKNOWN_CURRENCY_LABEL
    assert late["unattributed_reasons"] == [lp.UNATTRIBUTED_NO_MARKET_PRICE]


def test_cash_fx_is_declared_not_modelled() -> None:
    assert attribute(build(), None)["cash_fx_modelled"] is False
