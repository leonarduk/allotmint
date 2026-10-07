import datetime as dt
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.common import instrument_api
from backend.common import portfolio_utils as pu


@pytest.fixture
def portfolio_series():
    base = date(2024, 1, 1)
    idx = pd.Index([base + timedelta(days=i) for i in range(3)])
    return pd.Series([1000.0, 1050.0, 1100.0], index=idx)


@pytest.fixture
def ledger_owner(monkeypatch):
    """Back the single-owner TWR/XIRR path with an in-memory ledger and closes (#8461).

    Call it with ``(transactions, closes, trade_cash=True)``; ``closes`` maps
    an instrument key to ``{"YYYY-MM-DD": gbp_close}``.
    """

    def install(transactions, closes, *, trade_cash=True):
        monkeypatch.setattr(
            pu.portfolio_mod,
            "build_owner_portfolio",
            lambda owner, *, pricing_date=None, **_: {"accounts": []},
        )
        ledgers = [pu.ledger_performance.AccountLedger("isa", transactions, trade_cash)] if transactions else []
        monkeypatch.setattr(pu.ledger_performance, "load_owner_ledgers", lambda owner: ledgers)

        def load(key, start, end):
            points = closes.get(key, {})
            return pd.Series({pd.Timestamp(day): price for day, price in points.items()}, dtype=float)

        monkeypatch.setattr(pu.ledger_performance, "load_gbp_closes", load)

    return install


def _deposit(day, pounds):
    return {"date": day, "type": "DEPOSIT", "amount_minor": int(pounds * 100)}


def _buy(day, units, pounds):
    return {"date": day, "type": "BUY", "ticker": "AAA.L", "units": units, "amount_minor": int(pounds * 100)}


# One GBP instrument; see tests/backend/common/test_ledger_performance.py for the hand-worked figures.
LEDGER_END = date(2026, 2, 27)
LEDGER_CLOSES = {"AAA.L": {"2026-01-29": 100.0, "2026-01-30": 110.0, "2026-02-12": 99.0}}
LEDGER_TRANSACTIONS = [
    _deposit("2026-01-29", 1000),
    _buy("2026-01-29", 10, 1000),
    _deposit("2026-02-11", 1100),
    _buy("2026-02-12", 10, 1100),
    {"date": "2026-02-13", "type": "DIVIDEND", "amount_minor": 3000},
]


def test_compute_time_weighted_return_with_cashflows(ledger_owner):
    """#8461: the deposits (£2,100 in, £2,010 held at the end) are not a loss.

    +10% in January, -10% on 12 Feb, then the £30 dividend:
    1.1 * 0.9 * 2010 / 1980 - 1 = 2010 / 2000 - 1.
    """
    ledger_owner(LEDGER_TRANSACTIONS, LEDGER_CLOSES)

    result = pu.compute_time_weighted_return("owner", 365, pricing_date=LEDGER_END)

    assert result == pytest.approx(2010 / 2000 - 1)


def test_compute_time_weighted_return_window_uses_calendar_days(ledger_owner):
    ledger_owner(LEDGER_TRANSACTIONS, LEDGER_CLOSES)

    # 16 days before 27 Feb is 11 Feb, so the window is 12 Feb onwards.
    result = pu.compute_time_weighted_return("owner", 16, pricing_date=LEDGER_END)

    assert result == pytest.approx(0.9 * 2010 / 1980 - 1)


def test_compute_time_weighted_return_deposit_is_neutral(ledger_owner):
    """#8461: a mid-window deposit with flat prices must leave TWR at zero,
    where the old current-holdings series read it as a loss of the deposit.
    """
    closes = {"AAA.L": {"2026-01-05": 100.0}}
    ledger_owner([_deposit("2026-01-05", 1000), _buy("2026-01-05", 10, 1000), _deposit("2026-01-20", 500)], closes)

    result = pu.compute_time_weighted_return("owner", 365, pricing_date=date(2026, 2, 2))

    assert result == pytest.approx(0.0)


def test_compute_time_weighted_return_withdrawal_is_neutral(ledger_owner):
    """#8461: a mid-window withdrawal must not read as a gain (or a loss).

    £1,500 in, £1,000 of it in 10 units that rise 10% on 12 Jan, then £500
    withdrawn on 20 Jan with flat prices: TWR is the 12 Jan move only.
    """
    closes = {"AAA.L": {"2026-01-05": 100.0, "2026-01-12": 110.0}}
    transactions = [
        _deposit("2026-01-05", 1500),
        _buy("2026-01-05", 10, 1000),
        {"date": "2026-01-20", "type": "WITHDRAWAL", "amount_minor": 50000},
    ]
    ledger_owner(transactions, closes)

    result = pu.compute_time_weighted_return("owner", 365, pricing_date=date(2026, 2, 2))

    assert result == pytest.approx(1600 / 1500 - 1)


def test_compute_time_weighted_return_dividend_is_return(ledger_owner):
    closes = {"AAA.L": {"2026-01-05": 100.0}}
    transactions = [
        _deposit("2026-01-05", 1000),
        _buy("2026-01-05", 10, 1000),
        {"date": "2026-01-20", "type": "DIVIDEND", "ticker": "AAA.L", "amount_minor": 3000},
    ]
    ledger_owner(transactions, closes)

    result = pu.compute_time_weighted_return("owner", 365, pricing_date=date(2026, 2, 2))

    assert result == pytest.approx(0.03)


def test_compute_time_weighted_return_unknown_owner_raises(monkeypatch):
    def missing(owner, *, pricing_date=None, **_):
        raise FileNotFoundError(owner)

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", missing)

    with pytest.raises(FileNotFoundError):
        pu.compute_time_weighted_return("ghost")
    with pytest.raises(FileNotFoundError):
        pu.compute_xirr("ghost")


def test_compute_time_weighted_return_requires_two_points(monkeypatch, ledger_owner):
    """No dated ledger rows: falls back to the current-holdings series."""
    ledger_owner([], {})
    idx = pd.Index([date(2024, 1, 1)])
    series = pd.Series([1000.0], index=idx)
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: [])

    assert pu.compute_time_weighted_return("owner") is None


def test_compute_time_weighted_return_without_ledger_uses_holdings_series(monkeypatch, ledger_owner, portfolio_series):
    ledger_owner([], {})
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: portfolio_series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: [])

    assert pu.compute_time_weighted_return("owner") == pytest.approx(0.10)


@pytest.fixture
def one_year_series():
    start = date(2024, 1, 1)
    end = date(2025, 1, 1)
    idx = pd.Index([start, end])
    return pd.Series([1000.0, 1100.0], index=idx)


def test_compute_xirr_simple_contribution(ledger_owner):
    """£1,000 invested on 1 Jan 2025 is worth £1,100 a year later: 10%."""
    closes = {"AAA.L": {"2025-01-01": 100.0, "2026-01-01": 110.0}}
    ledger_owner([_deposit("2025-01-01", 1000), _buy("2025-01-01", 10, 1000)], closes)

    result = pu.compute_xirr("owner", 365, pricing_date=date(2026, 1, 1))

    assert result == pytest.approx(0.10, abs=1e-6)


def test_ledger_xirr_flows_open_with_window_value(ledger_owner):
    """#8461: a window starting after inception opens with the value then held,
    and a later deposit is an investor outflow on its own day.
    """
    closes = {"AAA.L": {"2025-01-01": 100.0, "2025-06-02": 105.0, "2026-01-01": 120.0}}
    transactions = [_deposit("2025-01-01", 1000), _buy("2025-01-01", 10, 1000), _deposit("2025-09-01", 500)]
    ledger_owner(transactions, closes)
    perf = pu._owner_ledger_performance("owner", date(2026, 1, 1))

    flows = pu._ledger_xirr_flows(perf, 213)  # window opens 2 Jun 2025

    assert flows == [
        (date(2025, 6, 2), pytest.approx(-1050.0)),
        (date(2025, 9, 1), pytest.approx(-500.0)),
        (date(2026, 1, 1), pytest.approx(1700.0)),
    ]


def test_ledger_xirr_flows_weekend_window_start_opens_on_prior_close(ledger_owner):
    """#8461: a window starting on a Saturday opens with Friday's close, dated Friday.

    TWR's first chained return (Monday) divides by Friday's close, so the
    XIRR opening outflow is dated on that close too; dating it on the
    Saturday would shorten the holding period by a day and overstate XIRR.
    """
    end = date(2026, 1, 1)
    closes = {"AAA.L": {"2025-01-01": 100.0, "2025-06-06": 105.0, "2026-01-01": 120.0}}
    ledger_owner([_deposit("2025-01-01", 1000), _buy("2025-01-01", 10, 1000)], closes)
    days = (end - date(2025, 6, 7)).days  # window opens after Saturday 7 Jun 2025
    perf = pu._owner_ledger_performance("owner", end)

    flows = pu._ledger_xirr_flows(perf, days)

    assert flows == [
        (date(2025, 6, 6), pytest.approx(-1050.0)),
        (end, pytest.approx(1200.0)),
    ]
    twr = pu.compute_time_weighted_return("owner", days, pricing_date=end)
    assert twr == pytest.approx(1200 / 1050 - 1)
    held_days = (end - date(2025, 6, 6)).days
    assert pu.compute_xirr("owner", days, pricing_date=end) == pytest.approx(
        (1 + twr) ** (365 / held_days) - 1, abs=1e-6
    )


def test_ledger_xirr_flows_zero_opening_value_has_no_opening_outflow(ledger_owner):
    """Everything sold and withdrawn before the window: no opening outflow.

    A zero opening flow would add nothing to the NPV, so it is dropped; the
    re-entry deposit is then the first investor outflow. 5 units bought at
    100 and closing at 120 is +20% over 1 Sep 2025 - 1 Jan 2026.
    """
    end = date(2026, 1, 1)
    closes = {"AAA.L": {"2025-01-02": 100.0, "2025-09-01": 100.0, "2026-01-01": 120.0}}
    transactions = [
        _deposit("2025-01-02", 1000),
        _buy("2025-01-02", 10, 1000),
        {"date": "2025-02-03", "type": "SELL", "ticker": "AAA.L", "units": 10, "amount_minor": 100000},
        {"date": "2025-02-03", "type": "WITHDRAWAL", "amount_minor": 100000},
        _deposit("2025-09-01", 500),
        _buy("2025-09-01", 5, 500),
    ]
    ledger_owner(transactions, closes)
    perf = pu._owner_ledger_performance("owner", end)

    flows = pu._ledger_xirr_flows(perf, 213)  # window opens after 2 Jun 2025, value 0 then

    assert flows == [
        (date(2025, 9, 1), pytest.approx(-500.0)),
        (end, pytest.approx(600.0)),
    ]
    held_days = (end - date(2025, 9, 1)).days
    assert pu.compute_xirr("owner", 213, pricing_date=end) == pytest.approx(1.2 ** (365 / held_days) - 1, abs=1e-6)


def test_ledger_xirr_flows_close_dated_on_last_rebuilt_day(ledger_owner):
    """A weekend ``end`` passed straight to the rebuild closes on Friday's value, dated Friday."""
    closes = {"AAA.L": {"2025-01-01": 100.0, "2026-01-02": 110.0}}
    ledger_owner([_deposit("2025-01-01", 1000), _buy("2025-01-01", 10, 1000)], closes)
    ledgers = pu.ledger_performance.load_owner_ledgers("owner")
    perf = pu.ledger_performance.build_ledger_performance(ledgers, date(2026, 1, 3))  # Saturday

    flows = pu._ledger_xirr_flows(perf, 0)

    assert flows == [
        (date(2025, 1, 1), pytest.approx(-1000.0)),
        (date(2026, 1, 2), pytest.approx(1100.0)),
    ]


def test_ledger_xirr_flows_untracked_cash_pays_out_income(ledger_owner):
    """Without trade cash, buys are investor outflows and dividends inflows."""
    closes = {"AAA.L": {"2025-01-01": 100.0}}
    transactions = [_buy("2025-01-01", 10, 1000), {"date": "2025-07-01", "type": "DIVIDEND", "amount_minor": 5000}]
    ledger_owner(transactions, closes, trade_cash=False)
    perf = pu._owner_ledger_performance("owner", date(2026, 1, 1))

    flows = pu._ledger_xirr_flows(perf, 0)

    assert flows == [
        (date(2025, 1, 1), pytest.approx(-1000.0)),
        (date(2025, 7, 1), pytest.approx(50.0)),
        (date(2026, 1, 1), pytest.approx(1000.0)),
    ]


def test_compute_xirr_requires_cashflows(monkeypatch, ledger_owner, one_year_series):
    """No dated ledger rows: the fallback has only a closing value, so no XIRR."""
    ledger_owner([], {})
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: one_year_series,
    )
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: [])

    assert pu.compute_xirr("owner") is None


def test_compute_cagr(monkeypatch, one_year_series):
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: one_year_series,
    )

    result = pu.compute_cagr("owner")

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_cagr_invalid_series(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    series = pd.Series([0.0, 1000.0], index=idx)
    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda owner, days=365, *, pricing_date=None, **_: series,
    )

    assert pu.compute_cagr("owner") is None


def test_compute_cash_apy(monkeypatch):
    idx = pd.Index([date(2024, 1, 1), date(2025, 1, 1)])
    cash_series = pd.Series([5000.0, 5250.0], index=idx)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: cash_series)

    result = pu.compute_cash_apy("owner")

    assert result == pytest.approx(0.05, abs=1e-3)


def test_compute_cash_apy_empty(monkeypatch):
    empty_series = pd.Series(dtype=float)
    monkeypatch.setattr(pu, "_cash_value_series", lambda owner, days=365: empty_series)

    assert pu.compute_cash_apy("owner") is None


@pytest.fixture
def sample_portfolio():
    return {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "ABC", "units": "1.2", "exchange": "L"},
                    {"ticker": "ABC", "units": 0.8},  # missing exchange -> resolved
                    {"ticker": "MNO", "units": 5},  # price lookup will fail
                    {"ticker": "ZERO", "units": 0},  # zero units should be ignored
                ]
            },
            {
                "holdings": [
                    {"ticker": "DEF.US", "units": 2.3456},
                    {"ticker": "DEF", "units": "1.0", "exchange": "US"},
                ]
            },
        ]
    }


def test_portfolio_value_breakdown_aggregates_and_handles_missing(monkeypatch, sample_portfolio):
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: sample_portfolio,
    )

    resolved = {
        "ABC": ("ABC", "L"),
        "DEF.US": ("DEF", "US"),
        "DEF": ("DEF", "US"),
    }

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: resolved.get(ticker),
    )

    prices = {
        ("ABC", "L"): 10.12345,
        ("DEF", "US"): 50.98765,
    }

    def fake_get_price_for_date_scaled(ticker, exchange, target):
        price = prices.get((ticker, exchange))
        if price is None:
            return None, None
        return price, "test"

    monkeypatch.setattr(pu, "_get_price_for_date_scaled", fake_get_price_for_date_scaled)

    rows = pu.portfolio_value_breakdown("owner", "2024-05-01")

    rows_by_key = {(row["ticker"], row["exchange"]): row for row in rows}

    assert ("ZERO", "L") not in rows_by_key
    assert {key for key in rows_by_key} == {("ABC", "L"), ("DEF", "US"), ("MNO", "L")}

    abc = rows_by_key[("ABC", "L")]
    assert abc["units"] == pytest.approx(2.0)
    assert abc["price"] == pytest.approx(10.1235)
    assert abc["value"] == pytest.approx(20.25)

    deff = rows_by_key[("DEF", "US")]
    assert deff["units"] == pytest.approx(3.3456)
    assert deff["price"] == pytest.approx(50.9877)
    assert deff["value"] == pytest.approx(170.58)

    mno = rows_by_key[("MNO", "L")]
    assert mno["units"] == pytest.approx(5.0)
    assert mno["price"] is None
    assert mno["value"] is None


def test_portfolio_value_breakdown_invalid_date(monkeypatch):
    called = False

    def fake_builder(owner, *, pricing_date=None, **_):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", fake_builder)

    with pytest.raises(ValueError) as excinfo:
        pu.portfolio_value_breakdown("owner", "not-a-date")

    assert str(excinfo.value) == "Invalid date: not-a-date"
    assert called is False


def test_compute_owner_performance_respects_flagged_and_cash(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "FLAG.L", "units": 1},
                    {"ticker": "NORM.L", "units": 1},
                    {"ticker": "CASH.GBP", "units": 1},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {
            "FLAG.L": {"flagged": True},
            "NORM.L": {"flagged": False},
            "CASH.GBP": {"flagged": False},
        },
        raising=False,
    )

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    frames = {
        ("FLAG", "L"): pd.DataFrame({"Date": dates, "Close": [5.0, 6.0]}),
        ("NORM", "L"): pd.DataFrame({"Date": dates, "Close": [10.0, 11.0]}),
        ("CASH", "GBP"): pd.DataFrame({"Date": dates, "Close": [0.01, 0.01]}),
    }

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return frames.get((ticker, exchange), pd.DataFrame()).copy()

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    excluded = pu.compute_owner_performance("owner", days=10, include_flagged=False, include_cash=False)
    included_flagged = pu.compute_owner_performance("owner", days=10, include_flagged=True, include_cash=False)
    included_cash = pu.compute_owner_performance("owner", days=10, include_flagged=False, include_cash=True)

    assert [row["value"] for row in excluded["history"]] == [10.0, 11.0]
    assert [row["value"] for row in included_flagged["history"]] == [15.0, 17.0]
    assert [row["value"] for row in included_cash["history"]] == [11.0, 12.0]

    for payload in (excluded, included_flagged, included_cash):
        assert "reporting_date" in payload
        assert "previous_date" in payload
        date.fromisoformat(payload["reporting_date"])
        date.fromisoformat(payload["previous_date"])


def _flat_usd_rate(monkeypatch) -> None:
    """Store a flat 1.0 USD->GBP rate, so NYSE.N lines keep their native sums.

    ``compute_owner_performance`` converts USD lines at the stored rate
    (#9678); these holiday tests are about date alignment, not FX.
    """
    rates = pd.DataFrame({"Date": pd.date_range("2023-12-01", "2024-01-31"), "Rate": 1.0})
    monkeypatch.setattr(pu, "load_fx_history", lambda curr, start=None, end=None: rates)


def test_compute_owner_performance_forward_fills_exchange_holiday(monkeypatch):
    """Regression test for #6857: a single-exchange holiday (e.g. a UK bank
    holiday closing an LSE-listed holding while a NYSE-listed holding in the
    same portfolio keeps trading) must not be treated as the closed holding
    being worth £0 that day. Runs unconditionally in OSS CI -- no
    ``allotmint_pro`` required.
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "LSE.L", "units": 10},
                    {"ticker": "NYSE.N", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=3, freq="D")  # Mon, Tue, Wed
    # LSE.L has no row for the middle date (bank holiday); NYSE.N trades every day.
    lse_dates = pd.DatetimeIndex([all_dates[0], all_dates[2]])
    frames = {
        ("LSE", "L"): pd.DataFrame({"Date": lse_dates, "Close": [100.0, 102.0]}),
        ("NYSE", "N"): pd.DataFrame({"Date": all_dates, "Close": [50.0, 51.0, 52.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )
    _flat_usd_rate(monkeypatch)

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 100.0 + 5 * 50.0,  # 1250: both priced
            10 * 100.0 + 5 * 51.0,  # 1255: LSE.L holiday -> carries forward 100.0, not 0
            10 * 102.0 + 5 * 52.0,  # 1280: LSE.L reopens
        ]
    )
    # No fake crash-and-recover: the middle value sits between its
    # neighbours instead of collapsing toward zero.
    assert values[0] < values[1] < values[2]


def test_compute_owner_performance_forward_fills_multi_day_gap(monkeypatch):
    """Regression test for #6857: multi-day gaps (e.g. a Christmas/New Year
    week where one exchange is shut for several consecutive days) must also
    forward-fill correctly, not just single-day gaps.
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "LSE.L", "units": 10},
                    {"ticker": "NYSE.N", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=4, freq="D")  # Mon-Thu
    # LSE.L is shut for the middle two days (e.g. a holiday week); NYSE.N trades every day.
    lse_dates = pd.DatetimeIndex([all_dates[0], all_dates[3]])
    frames = {
        ("LSE", "L"): pd.DataFrame({"Date": lse_dates, "Close": [100.0, 104.0]}),
        ("NYSE", "N"): pd.DataFrame({"Date": all_dates, "Close": [50.0, 51.0, 52.0, 53.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )
    _flat_usd_rate(monkeypatch)

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 100.0 + 5 * 50.0,  # 1050
            10 * 100.0 + 5 * 51.0,  # 1255: LSE.L still shut -> carries forward 100.0
            10 * 100.0 + 5 * 52.0,  # 1260: LSE.L still shut -> carries forward 100.0
            10 * 104.0 + 5 * 53.0,  # 1305: LSE.L reopens
        ]
    )


def test_compute_owner_performance_leading_gap_contributes_zero(monkeypatch):
    """Regression test for #6857: a ticker with no price history yet at the
    start of the requested window should contribute 0 for those dates, not
    NaN (and not be forward-filled from nothing).
    """
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "OLD.L", "units": 10},
                    {"ticker": "NEW.L", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    all_dates = pd.date_range("2024-01-01", periods=3, freq="D")  # Mon, Tue, Wed
    new_dates = pd.DatetimeIndex([all_dates[2]])  # NEW.L only starts trading on day 3
    frames = {
        ("OLD", "L"): pd.DataFrame({"Date": all_dates, "Close": [10.0, 11.0, 12.0]}),
        ("NEW", "L"): pd.DataFrame({"Date": new_dates, "Close": [20.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames.get((ticker, exchange), pd.DataFrame()).copy(),
    )

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [row["value"] for row in result["history"]]
    assert values == pytest.approx(
        [
            10 * 10.0,  # NEW.L not trading yet -> contributes 0, not NaN
            10 * 11.0,
            10 * 12.0 + 5 * 20.0,
        ]
    )
    assert all(v == v for v in values)  # no NaNs leaked through


def test_compute_owner_performance_filters_single_day_zero(monkeypatch):
    pytest.importorskip("allotmint_pro")
    portfolio = {"accounts": [{"holdings": [{"ticker": "ERR.L", "units": 10}]}]}

    real_calc = pu.PricingDateCalculator

    def fake_calc(*args, **kwargs):
        return real_calc(today=dt.date(2024, 1, 10))

    monkeypatch.setattr(pu, "PricingDateCalculator", fake_calc)

    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    frames = {
        ("ERR", "L"): pd.DataFrame({"Date": dates, "Close": [100.0, 0.0, 102.0]}),
    }

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return frames.get((ticker, exchange), pd.DataFrame()).copy()

    monkeypatch.setattr(pu, "load_meta_timeseries", fake_load_meta_timeseries)

    result = pu.compute_owner_performance("owner", days=10)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result["history"][0]["value"] == pytest.approx(1000.0)
    assert result["history"][1]["value"] == pytest.approx(1010.0)
    assert result["history"][2]["value"] == pytest.approx(1020.0)

    issues = result["data_quality_issues"]
    assert issues == [
        {
            "date": "2024-01-02",
            "value": 0.0,
            "repaired_value": 1010.0,
            "previous_value": 1000.0,
            "next_value": 1020.0,
        }
    ]


def test_compute_owner_performance_drops_partial_close_nans(monkeypatch):
    pytest.importorskip("allotmint_pro")
    portfolio = {"accounts": [{"holdings": [{"ticker": "NAN.L", "units": 2}, {"ticker": "CASH.GBP", "units": 1}]}]}
    monkeypatch.setattr(
        pu.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: portfolio,
    )
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    frames = {
        ("NAN", "L"): pd.DataFrame({"Date": dates, "Close": [10.0, float("nan"), 11.0]}),
        ("CASH", "GBP"): pd.DataFrame({"Date": dates, "Close": [0.01, 99.0, 1.0]}),
    }

    monkeypatch.setattr(
        pu,
        "load_meta_timeseries",
        lambda ticker, exchange, days: frames[(ticker, exchange)].copy(),
    )

    result = pu.compute_owner_performance("owner", days=10, include_cash=True)

    assert [row["date"] for row in result["history"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert [row["value"] for row in result["history"]] == [21.0, 22.0, 23.0]


def test_cash_flow_signs_treat_dividend_singular_same_as_plural():
    """Regression test for #4948: backend/common/dividends.py writes the
    ``DIVIDEND`` (singular) transaction type, but the TWR/XIRR cash-flow sign
    table previously only recognised ``DIVIDENDS`` (plural), silently
    excluding automated dividend transactions from return calculations.
    """

    assert "DIVIDEND" in pu._CASH_FLOW_SIGNS
    assert pu._CASH_FLOW_SIGNS["DIVIDEND"] == pu._CASH_FLOW_SIGNS["DIVIDENDS"]


def test_group_transactions_merges_members_and_skips_missing(monkeypatch):
    """#7228: group TWR/XIRR need cash flows pooled across every member,
    the same way the group portfolio pools holdings.
    """

    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy", "ghost"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
        "lucy": [{"date": "2024-01-03", "type": "withdrawal", "amount_minor": 200}],
    }

    def fake_load_transactions(owner, *, scaffold_missing=False):
        if owner not in per_owner_txs:
            raise FileNotFoundError(owner)
        return per_owner_txs[owner]

    monkeypatch.setattr(pu, "load_transactions", fake_load_transactions)

    merged, missing = pu._group_transactions("all")

    assert merged == per_owner_txs["steve"] + per_owner_txs["lucy"]
    assert missing == ["ghost"]


def test_group_transactions_missing_member_logs_warning(monkeypatch, caplog):
    """#7228 review MUST FIX 1: a missing ledger must not be silent -- their
    holdings still count toward the combined value series (via
    build_group_portfolio), so dropping their cash flows here would inflate
    TWR/XIRR with no signal to the user. At minimum this must be logged.
    """

    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "ghost"])
    monkeypatch.setattr(
        pu,
        "load_transactions",
        lambda owner, *, scaffold_missing=False: (
            [] if owner == "steve" else (_ for _ in ()).throw(FileNotFoundError(owner))
        ),
    )

    with caplog.at_level("WARNING", logger=pu.logger.name):
        merged, missing = pu._group_transactions("all")

    assert missing == ["ghost"]
    assert merged == []
    assert any("ghost" in record.getMessage() for record in caplog.records)


def test_compute_owner_performance_group_uses_group_portfolio(monkeypatch):
    """#7228: with group=True the group aggregation helper (the same one
    /portfolio-group/{slug} uses) supplies the combined holdings instead of
    a single owner's holdings -- the owner-scoped path must be untouched.
    """

    group_portfolio_dict = {
        "accounts": [{"holdings": [{"ticker": "NORM.L", "units": 3}]}],
    }

    def unexpected_owner_lookup(owner, *, pricing_date=None, **_):
        raise AssertionError("group=True must not call build_owner_portfolio")

    monkeypatch.setattr(pu.portfolio_mod, "build_owner_portfolio", unexpected_owner_lookup)
    monkeypatch.setattr(
        pu.group_portfolio,
        "build_group_portfolio",
        lambda slug, *, pricing_date=None: group_portfolio_dict if slug == "all" else {},
    )
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)) if "." in ticker else (ticker, None),
    )

    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    frame = pd.DataFrame({"Date": dates, "Close": [10.0, 11.0]})
    monkeypatch.setattr(pu, "load_meta_timeseries", lambda ticker, exchange, days: frame.copy())

    result = pu.compute_owner_performance("all", days=10, group=True)

    assert [row["value"] for row in result["history"]] == [30.0, 33.0]


def test_compute_owner_performance_group_unknown_slug_raises(monkeypatch):
    def raise_unknown(slug, *, pricing_date=None):
        raise ValueError(f"Unknown group slug: {slug!r}")

    monkeypatch.setattr(pu.group_portfolio, "build_group_portfolio", raise_unknown)

    with pytest.raises(ValueError):
        pu.compute_owner_performance("bogus", group=True)


def _forbid_ledger_rebuild(monkeypatch):
    """No group member has a ledger, so groups fall back to the legacy series (#9169).

    The current-holdings series and its include_missing_members contract
    (#7228) then apply; the rebuild itself must not run.
    """

    def no_ledger_rebuild(*args, **kwargs):
        raise AssertionError("a group with no member ledgers must not run the ledger rebuild")

    monkeypatch.setattr(pu, "_owner_ledger_performance", no_ledger_rebuild)
    monkeypatch.setattr(pu.ledger_performance, "load_owner_ledgers", lambda owner: [])
    monkeypatch.setattr(pu.ledger_performance, "build_ledger_performance", no_ledger_rebuild)


def test_compute_time_weighted_return_group_pools_member_cashflows(monkeypatch, portfolio_series):
    """#7228 review MUST FIX 3: pin the exact combined figure (not just
    "differs from the single-owner result") -- hand-computed below by
    replaying the same day-by-day chain-linking compute_time_weighted_return
    itself uses, with the two members' deposits pooled on the same day.
    """

    def fake_series(name, days=365, *, group=False, pricing_date=None):
        assert name == "all"
        assert group is True
        return portfolio_series

    monkeypatch.setattr(pu, "_portfolio_value_series", fake_series)
    _forbid_ledger_rebuild(monkeypatch)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
        "lucy": [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}],
    }
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: per_owner_txs[owner])

    group_result = pu.compute_time_weighted_return("all", group=True)

    # portfolio_series is [1000, 1050, 1100] on 2024-01-01/02/03.
    # amount_minor is pence, so each 1000-minor deposit is £10; pooled across
    # both members that's a £20 same-day flow on day 2, day 3 has no flow.
    # Chain-linking those two daily returns by hand:
    #   r1 = (1050 - 20) / 1000 - 1 = 0.03; r2 = 1100 / 1050 - 1 = 1/21
    #   twr = (1 + r1) * (1 + r2) - 1 = 1.03 * 22/21 - 1
    assert group_result == pytest.approx(0.07904761904761903)


def test_compute_time_weighted_return_group_reports_missing_members(monkeypatch, portfolio_series):
    """#7228 review MUST FIX 1: a missing member ledger must be surfaced,
    not silently folded into the figure -- their holdings still count via
    build_group_portfolio, so the caller needs to know the flows are
    incomplete.
    """

    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda name, days=365, *, group=False, pricing_date=None: portfolio_series,
    )
    _forbid_ledger_rebuild(monkeypatch)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "ghost"])
    monkeypatch.setattr(
        pu,
        "load_transactions",
        lambda owner, *, scaffold_missing=False: (
            [{"date": "2024-01-02", "type": "deposit", "amount_minor": 1000}]
            if owner == "steve"
            else (_ for _ in ()).throw(FileNotFoundError(owner))
        ),
    )

    value, missing = pu.compute_time_weighted_return("all", group=True, include_missing_members=True)

    assert missing == ["ghost"]
    assert value is not None


def test_compute_xirr_group_pools_member_cashflows(monkeypatch, one_year_series):
    def fake_series(name, days=365, *, group=False, pricing_date=None):
        assert name == "all"
        assert group is True
        return one_year_series

    monkeypatch.setattr(pu, "_portfolio_value_series", fake_series)
    _forbid_ledger_rebuild(monkeypatch)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "lucy"])

    per_owner_txs = {
        "steve": [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 50000}],
        "lucy": [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 50000}],
    }
    monkeypatch.setattr(pu, "load_transactions", lambda owner, *, scaffold_missing=False: per_owner_txs[owner])

    result = pu.compute_xirr("all", group=True)

    assert result == pytest.approx(0.10, abs=1e-3)


def test_compute_xirr_group_reports_missing_members(monkeypatch, one_year_series):
    """#7228 review MUST FIX 1: same partial-data signal as TWR."""

    monkeypatch.setattr(
        pu,
        "_portfolio_value_series",
        lambda name, days=365, *, group=False, pricing_date=None: one_year_series,
    )
    _forbid_ledger_rebuild(monkeypatch)
    monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: ["steve", "ghost"])
    monkeypatch.setattr(
        pu,
        "load_transactions",
        lambda owner, *, scaffold_missing=False: (
            [{"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 100000}]
            if owner == "steve"
            else (_ for _ in ()).throw(FileNotFoundError(owner))
        ),
    )

    value, missing = pu.compute_xirr("all", group=True, include_missing_members=True)

    assert missing == ["ghost"]
    assert value is not None


@pytest.fixture
def group_ledgers(monkeypatch):
    """Back the group TWR/XIRR path with in-memory member ledgers (#9169).

    Call it with ``(per_member, closes)``: ``per_member`` maps each group
    member to their transactions (``None`` for a member with no ledger) and
    ``closes`` is as for ``ledger_owner``. Each member has one tracked-cash
    account.
    """

    def install(per_member, closes):
        monkeypatch.setattr(pu.group_portfolio, "group_members", lambda slug: list(per_member))
        monkeypatch.setattr(
            pu.group_portfolio, "build_group_portfolio", lambda slug, *, pricing_date=None: {"accounts": []}
        )

        def load_ledgers(owner):
            transactions = per_member[owner]
            return [pu.ledger_performance.AccountLedger("isa", transactions, True)] if transactions else []

        monkeypatch.setattr(pu.ledger_performance, "load_owner_ledgers", load_ledgers)

        def load(key, start, end):
            points = closes.get(key, {})
            return pd.Series({pd.Timestamp(day): price for day, price in points.items()}, dtype=float)

        monkeypatch.setattr(pu.ledger_performance, "load_gbp_closes", load)

        def no_legacy_series(*args, **kwargs):
            raise AssertionError("a group with member ledgers must use the pooled ledger rebuild (#9169)")

        monkeypatch.setattr(pu, "_portfolio_value_series", no_legacy_series)

    return install


GROUP_END = date(2026, 2, 2)
FLAT_CLOSES = {"AAA.L": {"2026-01-05": 100.0}}


def test_group_twr_deposit_is_neutral(group_ledgers):
    """#9169: one member's mid-window deposit, flat prices: TWR is zero, not a loss."""
    group_ledgers(
        {
            "steve": [_deposit("2026-01-05", 1000), _buy("2026-01-05", 10, 1000)],
            "lucy": [_deposit("2026-01-20", 500)],
        },
        FLAT_CLOSES,
    )

    value, missing = pu.compute_time_weighted_return(
        "all", 365, pricing_date=GROUP_END, group=True, include_missing_members=True
    )

    assert value == pytest.approx(0.0)
    assert missing == []


@pytest.mark.parametrize("income_type", ["DIVIDEND", "INTEREST"])
def test_group_twr_income_is_return(group_ledgers, income_type):
    """#9169: dividends and cash interest are return for a group, not contributions.

    £2,000 pooled (steve's 10 units, lucy's cash), flat prices, then £30 of
    income lands in lucy's cash: 2030 / 2000 - 1.
    """
    group_ledgers(
        {
            "steve": [_deposit("2026-01-05", 1000), _buy("2026-01-05", 10, 1000)],
            "lucy": [
                _deposit("2026-01-05", 1000),
                {"date": "2026-01-20", "type": income_type, "amount_minor": 3000},
            ],
        },
        FLAT_CLOSES,
    )

    assert pu.compute_time_weighted_return("all", 365, pricing_date=GROUP_END, group=True) == pytest.approx(0.015)


def test_group_transfer_between_members_nets_to_zero(group_ledgers):
    """#9169: units moved from one member to another are neither a flow nor a return.

    10 units bought at 100 rise to 110 on 12 Jan, then move from steve to
    lucy on 20 Jan: the group's TWR is just the 10% move.
    """
    closes = {"AAA.L": {"2026-01-05": 100.0, "2026-01-12": 110.0}}
    move = {"date": "2026-01-20", "ticker": "AAA.L", "units": 10}
    group_ledgers(
        {
            "steve": [_deposit("2026-01-05", 1000), _buy("2026-01-05", 10, 1000), {**move, "type": "TRANSFER_OUT"}],
            "lucy": [{**move, "type": "TRANSFER_IN"}],
        },
        closes,
    )

    perf, missing = pu._group_ledger_performance("all", GROUP_END)

    assert missing == []
    assert perf.flows[pd.Timestamp("2026-01-20")] == pytest.approx(0.0)
    assert perf.values.iloc[-1] == pytest.approx(1100.0)
    assert pu.compute_time_weighted_return("all", 365, pricing_date=GROUP_END, group=True) == pytest.approx(0.10)


def test_group_missing_member_is_left_out_and_reported(group_ledgers, caplog):
    """#9169: a member with no ledger drops out of the pooled rebuild and is reported.

    The figure is the other members' exact return (10%), not one inflated by
    holdings no recorded flow explains (#7228).
    """
    closes = {"AAA.L": {"2026-01-05": 100.0, "2026-01-12": 110.0}}
    group_ledgers({"steve": [_deposit("2026-01-05", 1000), _buy("2026-01-05", 10, 1000)], "ghost": None}, closes)

    with caplog.at_level("WARNING", logger=pu.logger.name):
        twr, twr_missing = pu.compute_time_weighted_return(
            "all", 365, pricing_date=GROUP_END, group=True, include_missing_members=True
        )
    xirr, xirr_missing = pu.compute_xirr("all", 0, pricing_date=GROUP_END, group=True, include_missing_members=True)

    assert twr == pytest.approx(0.10)
    assert twr_missing == xirr_missing == ["ghost"]
    assert xirr is not None
    assert any("ghost" in record.getMessage() for record in caplog.records)


def test_group_xirr_hand_worked_schedule(group_ledgers):
    """#9169: XIRR over the pooled members' flows.

    steve puts £1,000 into 10 units on 1 Jan 2025 that are worth £1,200 on
    1 Jan 2026; lucy deposits £1,000 of cash 182 days in. The investor flows
    are -1000 (day 0), -1000 (day 182) and +2200 (day 365), so r solves
    -1000 - 1000 / (1 + r) ** (182 / 365) + 2200 / (1 + r) = 0, i.e. about 13.46%.
    """
    closes = {"AAA.L": {"2025-01-01": 100.0, "2026-01-01": 120.0}}
    group_ledgers(
        {
            "steve": [_deposit("2025-01-01", 1000), _buy("2025-01-01", 10, 1000)],
            "lucy": [_deposit("2025-07-02", 1000)],
        },
        closes,
    )

    result = pu.compute_xirr("all", 365, pricing_date=date(2026, 1, 1), group=True)

    assert result == pytest.approx(0.13462697984706992, abs=1e-6)
