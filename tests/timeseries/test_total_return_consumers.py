"""Performance/risk consumers on total return; price/valuation consumers pinned to price (#9370, #9571)."""

from __future__ import annotations

import datetime as dt
import logging
import os

import pandas as pd
import pytest

import backend.common.portfolio as portfolio_mod
from backend.agent import trading_agent
from backend.common import instrument_api, ledger_performance, portfolio_utils
from backend.timeseries import cache as ts_cache
from backend.timeseries import total_return as tr
from backend.timeseries.corporate_actions import (
    ACTION_COLUMNS,
    CONFIRMED_FROM,
    corporate_actions_path,
    load_dividends,
    stored_dividends,
)
from backend.utils import scenario_tester

DATES = pd.bdate_range("2024-03-04", periods=5)
# 100 -> ex-date close 98 with a 2.00 dividend: the total return is flat that day.
CLOSES = [100.0, 98.0, 99.0, 99.0, 100.0]
EX_DATE = DATES[1]
TOTAL_LEVELS = [100.0, 100.0, 100.0 * 99.0 / 98.0, 100.0 * 99.0 / 98.0, 100.0 * 100.0 / 98.0]


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the corporate-actions store at ``tmp_path``; return a writer for one ticker's file."""

    monkeypatch.setattr(ts_cache, "_CACHE_BASE", str(tmp_path))
    tr._report_price_fallback.cache_clear()

    def write(
        ticker: str,
        exchange: str,
        dividends: dict | None = None,
        *,
        splits: dict | None = None,
        confirmed_from: str | None = None,
    ) -> None:
        rows = [(pd.Timestamp(d), "dividend", v) for d, v in (dividends or {}).items()]
        rows += [(pd.Timestamp(d), "split", v) for d, v in (splits or {}).items()]
        frame = pd.DataFrame(
            [{"Date": d, "Action": a, "Value": v, "Currency": "GBP", "Source": "test"} for d, a, v in rows],
            columns=ACTION_COLUMNS,
        )
        frame["Date"] = frame["Date"].astype("datetime64[ms]")
        if confirmed_from is not None:
            frame.attrs[CONFIRMED_FROM] = confirmed_from
        path = corporate_actions_path(ticker, exchange)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        frame.to_parquet(path, index=False)

    return write


def _closes() -> pd.Series:
    return pd.Series(CLOSES, index=DATES)


def _frame(**extra) -> pd.DataFrame:
    return pd.DataFrame({"Date": DATES, "Close": CLOSES, **extra})


# ───────────────────────────── shared helper ──────────────────────────────


def test_stored_dividends_tells_no_file_from_no_dividends(store):
    store("PAY", "L", {EX_DATE: 2.0})
    store("NODIV", "L", splits={EX_DATE: 2.0})

    assert stored_dividends("MISSING", "L") is None
    assert load_dividends("MISSING", "L").empty  # the old loader still reads "nothing stored" as empty
    nodiv = stored_dividends("NODIV", "L")
    assert nodiv is not None and nodiv.empty
    assert stored_dividends("PAY", "L").tolist() == [2.0]


def test_total_return_closes_reinvests_stored_dividends(store):
    store("PAY", "L", {EX_DATE: 2.0})

    levels, basis = tr.total_return_closes(_closes(), "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(TOTAL_LEVELS)
    assert levels.index.equals(DATES)


def test_file_without_dividends_is_a_genuine_total_return(store):
    store("NODIV", "L", splits={DATES[3]: 2.0})

    levels, basis = tr.total_return_closes(_closes(), "NODIV", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(CLOSES)


def test_empty_file_confirmed_before_the_first_close_is_total_return(store):
    """A fetch that confirmed no dividends ever is a genuine total return (#9567)."""
    store("NONE", "N", confirmed_from="2000-01-03")

    dividends = stored_dividends("NONE", "N")
    assert dividends is not None and dividends.empty
    assert dividends.attrs[CONFIRMED_FROM] == pd.Timestamp("2000-01-03")
    levels, basis = tr.total_return_closes(_closes(), "NONE", "N")
    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(CLOSES)
    out, frame_basis = tr.total_return_frame(_frame(), "NONE", "N")
    assert frame_basis == tr.TOTAL_RETURN_BASIS
    assert out["Close"].tolist() == pytest.approx(CLOSES)


def test_empty_file_confirmed_within_the_grace_of_the_first_close_is_total(store):
    store("NONE", "N", confirmed_from=(DATES[0] + pd.Timedelta(days=6)).date().isoformat())

    assert tr.total_return_closes(_closes(), "NONE", "N")[1] == tr.TOTAL_RETURN_BASIS


def test_empty_file_confirmed_only_after_the_first_close_is_price(store, caplog):
    """A rolling fetch that saw no dividends in its last few days does not cover older closes."""
    store("RECENT", "L", confirmed_from="2024-06-03")
    closes = _closes()

    with caplog.at_level(logging.INFO, logger=tr.__name__):
        levels, basis = tr.total_return_closes(closes, "RECENT", "L")
        _, frame_basis = tr.total_return_frame(_frame(), "RECENT", "L")

    assert basis == tr.PRICE_RETURN_BASIS
    assert frame_basis == tr.PRICE_RETURN_BASIS
    assert levels is closes
    assert "only confirmed from 2024-06-03" in caplog.text
    # The same file covers a window of closes that starts after it.
    later = pd.Series(CLOSES, index=pd.bdate_range("2024-06-03", periods=5))
    assert tr.total_return_closes(later, "RECENT", "L")[1] == tr.TOTAL_RETURN_BASIS


def test_dividends_are_reinvested_whatever_the_confirmed_start(store):
    """``confirmed_from`` only qualifies a file with no dividends."""
    store("PAY", "L", {EX_DATE: 2.0}, confirmed_from="2024-06-03")

    levels, basis = tr.total_return_closes(_closes(), "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(TOTAL_LEVELS)


def test_missing_file_falls_back_to_price_and_reports_it(store, caplog):
    closes = _closes()

    with caplog.at_level(logging.INFO, logger=tr.__name__):
        levels, basis = tr.total_return_closes(closes, "MISSING", "L")

    assert basis == tr.PRICE_RETURN_BASIS
    assert levels is closes
    assert "Price return used for MISSING.L" in caplog.text


def test_unsafe_or_bare_ticker_falls_back_to_price(store):
    assert tr.total_return_closes(_closes(), "BAD/../X", "L")[1] == tr.PRICE_RETURN_BASIS
    assert tr.total_return_closes_for(_closes(), "PAY")[1] == tr.PRICE_RETURN_BASIS


def test_total_return_closes_for_splits_the_full_ticker(store):
    store("PAY", "L", {EX_DATE: 2.0})

    levels, basis = tr.total_return_closes_for(_closes(), "pay.l")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(TOTAL_LEVELS)


def test_total_return_frame_scales_every_close_column_only(store):
    store("PAY", "L", {EX_DATE: 2.0})
    df = _frame(Close_gbp=[c * 0.5 for c in CLOSES], Open=CLOSES, Volume=[1, 2, 3, 4, 5])

    out, basis = tr.total_return_frame(df, "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert out["Close"].tolist() == pytest.approx(TOTAL_LEVELS)
    assert out["Close_gbp"].tolist() == pytest.approx([v * 0.5 for v in TOTAL_LEVELS])
    assert out["Open"].tolist() == CLOSES
    assert out["Volume"].tolist() == [1, 2, 3, 4, 5]
    assert df["Close"].tolist() == CLOSES  # input not mutated


def test_total_return_frame_reads_dates_from_the_index(store):
    store("PAY", "L", {EX_DATE: 2.0})
    df = pd.DataFrame({"Close": CLOSES}, index=DATES)

    out, basis = tr.total_return_frame(df, "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert out["Close"].tolist() == pytest.approx(TOTAL_LEVELS)


def test_total_return_frame_without_native_close_stays_on_price(store):
    store("PAY", "L", {EX_DATE: 2.0})
    df = pd.DataFrame({"Date": DATES, "Close_gbp": CLOSES})

    out, basis = tr.total_return_frame(df, "PAY", "L")

    assert basis == tr.PRICE_RETURN_BASIS
    assert out is df


def test_total_return_frame_scales_rows_by_label_not_position(store):
    """Out-of-order rows on a sliced (non-zero-based) index get their own date's factor."""
    store("PAY", "L", {EX_DATE: 2.0})
    df = _frame(Close_gbp=[c * 0.5 for c in CLOSES])
    df.index = range(10, 15)
    shuffled = df.iloc[[4, 0, 3, 1, 2]]

    out, basis = tr.total_return_frame(shuffled, "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    expected = dict(zip(range(10, 15), TOTAL_LEVELS))
    assert out.index.tolist() == shuffled.index.tolist()
    assert out["Close"].tolist() == pytest.approx([expected[i] for i in out.index])
    assert out["Close_gbp"].tolist() == pytest.approx([expected[i] * 0.5 for i in out.index])


def test_total_return_frame_without_dates_stays_on_price(store, caplog):
    """A RangeIndex frame with no Date column must not be read as 1970 dates and reported as total."""
    store("PAY", "L", {EX_DATE: 2.0})
    df = pd.DataFrame({"Close": CLOSES})

    with caplog.at_level(logging.INFO, logger=tr.__name__):
        out, basis = tr.total_return_frame(df, "PAY", "L")

    assert basis == tr.PRICE_RETURN_BASIS
    assert out is df
    assert "no Date column or date index" in caplog.text


@pytest.mark.parametrize("tz", ["UTC", "Europe/London", "America/New_York"])
def test_total_return_frame_tz_aware_dates_match_naive_dividends(store, tz):
    store("PAY", "L", {EX_DATE: 2.0})
    df = pd.DataFrame({"Date": DATES.tz_localize(tz), "Close": CLOSES})

    out, basis = tr.total_return_frame(df, "PAY", "L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert out["Close"].tolist() == pytest.approx(TOTAL_LEVELS)


def test_total_return_closes_tz_aware_dividends_match_naive_closes(store):
    dividends = pd.Series([2.0], index=pd.DatetimeIndex([EX_DATE]).tz_localize("UTC"))

    levels, basis = tr.total_return_closes(_closes(), "PAY", "L", load_dividends=lambda t, e: dividends)

    assert basis == tr.TOTAL_RETURN_BASIS
    assert levels.tolist() == pytest.approx(TOTAL_LEVELS)


# ───────────────────────────── scenarios ──────────────────────────────


def _range_loader(frames: dict):
    def load(ticker, exchange, start_date, end_date, **_kwargs):
        frame = frames.get(ticker)
        if frame is None:
            return pd.DataFrame()
        dates = pd.to_datetime(frame["Date"])
        return frame[(dates >= pd.Timestamp(start_date)) & (dates <= pd.Timestamp(end_date))].reset_index(drop=True)

    return load


def _no_scaling(monkeypatch):
    monkeypatch.setattr(scenario_tester, "get_scaling_override", lambda *a, **k: 1.0)


def test_forward_returns_use_total_return(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader({"PAY": _frame()}))
    _no_scaling(monkeypatch)

    # Event on the ex-date: the base is the pre-event close (DATES[0]).
    returns, basis = scenario_tester._forward_returns("PAY", "L", EX_DATE.date())

    assert basis == tr.TOTAL_RETURN_BASIS
    # 1 calendar day -> DATES[2]: price says -1% (99/100), total return +1.0% (99/98).
    assert returns["1d"] == pytest.approx(TOTAL_LEVELS[2] / 100.0 - 1.0)
    assert returns["1w"] is None  # the five-day fixture ends before a week has passed


def test_calc_return_uses_total_return(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader({"PAY": _frame()}))
    _no_scaling(monkeypatch)

    ret = scenario_tester._calc_return("PAY", "L", DATES[0].date(), 4)

    assert ret == pytest.approx(TOTAL_LEVELS[-1] / 100.0 - 1.0)


def test_calc_return_without_dates_returns_none(store, monkeypatch):
    """No Date column and a RangeIndex: no horizon check possible, so no return (not a TypeError)."""
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", lambda *a, **k: pd.DataFrame({"Close": CLOSES}))
    _no_scaling(monkeypatch)

    assert scenario_tester._calc_return("PAY", "L", DATES[0].date(), 4) is None


def test_historical_event_portfolio_reports_price_fallbacks(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    frames = {"PAY": _frame(), "NOFILE": _frame(), "PRX": _frame()}
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader(frames))
    _no_scaling(monkeypatch)
    portfolio = {
        "accounts": [
            {"holdings": [{"ticker": "PAY.L", "market_value_gbp": 100.0}]},
            {"holdings": [{"ticker": "NOFILE.L", "market_value_gbp": 100.0}]},
        ],
        "total_value_estimate_gbp": 200.0,
    }
    event = {"date": EX_DATE.date(), "proxy_index": "PRX.L"}

    result = scenario_tester.apply_historical_event_portfolio(portfolio, event)

    one_day = result["1d"]
    # From the pre-event close (100) to DATES[2]: PAY total return, NOFILE price 99.
    assert one_day["total_value_gbp"] == pytest.approx(TOTAL_LEVELS[2] + 99.0, abs=0.01)
    assert one_day["return_basis"] == tr.PRICE_RETURN_BASIS
    assert one_day["price_return_tickers"] == ["NOFILE.L"]


def test_historical_event_portfolio_all_total_return(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader({"PAY": _frame()}))
    _no_scaling(monkeypatch)
    portfolio = {"accounts": [{"holdings": [{"ticker": "PAY.L", "market_value_gbp": 100.0}]}]}

    result = scenario_tester.apply_historical_event_portfolio(portfolio, {"date": EX_DATE.date()})

    assert result["1d"]["total_value_gbp"] is not None
    assert result["1d"]["return_basis"] == tr.TOTAL_RETURN_BASIS
    assert result["1d"]["price_return_tickers"] == []
    # A horizon with no value has no basis to report.
    assert result["1y"]["total_value_gbp"] is None
    assert result["1y"]["return_basis"] is None


# ───────────────────────────── VaR ──────────────────────────────


def test_var_uses_total_returns_but_traded_last_price(store):
    store("PAY", "L", {DATES[1]: 5.0})
    df = pd.DataFrame({"Date": DATES, "Close": [100.0, 95.0, 95.0, 95.0, 95.0]})

    price_var, price_basis = portfolio_utils.compute_var_with_basis(df)
    total_var, total_basis = portfolio_utils.compute_var_with_basis(df, ticker="PAY", exchange="L")

    assert price_basis == tr.PRICE_RETURN_BASIS
    assert price_var == pytest.approx(-pd.Series([-0.05, 0, 0, 0]).quantile(0.05) * 95.0)
    # The 5.00 dividend offsets the 5.00 ex-date drop: no daily loss on a total-return basis.
    assert total_basis == tr.TOTAL_RETURN_BASIS
    assert total_var == pytest.approx(0.0)
    assert portfolio_utils.compute_var(df) == pytest.approx(price_var)


def test_var_without_corporate_actions_is_price_var(store):
    df = pd.DataFrame({"Date": DATES, "Close": CLOSES})

    var, basis = portfolio_utils.compute_var_with_basis(df, ticker="MISSING", exchange="L")

    assert basis == tr.PRICE_RETURN_BASIS
    assert var == pytest.approx(portfolio_utils.compute_var(df))


def test_custom_query_var_runs_on_total_returns(store, monkeypatch):
    """/custom-query/run end to end through the real compute_var_with_basis (no VaR mock)."""
    from backend.routes import query

    store("PAY", "L", {DATES[1]: 5.0})
    frame = pd.DataFrame({"Date": DATES, "Close": [100.0, 95.0, 95.0, 95.0, 95.0]})
    monkeypatch.setattr(query, "list_portfolios", lambda: [])
    monkeypatch.setattr(query, "load_meta_timeseries_range", lambda *a, **k: frame.copy())
    q = query.CustomQuery(
        start=DATES[0].date(), end=DATES[-1].date(), tickers=["PAY.L", "NOFILE.L"], metrics=[query.Metric.VAR]
    )

    rows = {row["ticker"]: row for row in query.run_query(q)["results"]}

    assert rows["PAY.L"]["return_basis"] == tr.TOTAL_RETURN_BASIS
    assert rows["PAY.L"]["var"] == pytest.approx(0.0)
    assert rows["NOFILE.L"]["return_basis"] == tr.PRICE_RETURN_BASIS
    assert rows["NOFILE.L"]["var"] == pytest.approx(portfolio_utils.compute_var(frame))


# ───────────────────────────── alpha / tracking error ──────────────────────────────


@pytest.fixture
def benchmark_env(store, monkeypatch):
    store("BENCH", "L", {EX_DATE: 2.0})
    portfolio = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=[d.date() for d in DATES])
    basis = {"portfolio_return_basis": tr.PRICE_RETURN_BASIS, "portfolio_price_basis_share": 1.0}
    monkeypatch.setattr(portfolio_utils, "_portfolio_return_series", lambda *a, **k: (portfolio, basis))
    frames = {"BENCH": _frame(), "NOFILE": _frame()}
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", lambda t, e, d: frames.get(t, pd.DataFrame()).copy())


def test_alpha_benchmark_side_is_total_return(benchmark_env):
    value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", "BENCH.L", include_breakdown=True)

    bench = TOTAL_LEVELS[-1] / 100.0 - 1.0
    assert breakdown["benchmark_cumulative_return"] == pytest.approx(bench)
    assert breakdown["portfolio_cumulative_return"] == pytest.approx(0.04)
    assert value == pytest.approx(0.04 - bench)
    assert breakdown["benchmark_return_basis"] == tr.TOTAL_RETURN_BASIS


def test_alpha_benchmark_without_actions_reports_price(benchmark_env):
    _value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", "NOFILE.L", include_breakdown=True)

    assert breakdown["benchmark_cumulative_return"] == pytest.approx(0.0)
    assert breakdown["benchmark_return_basis"] == tr.PRICE_RETURN_BASIS


def test_tracking_error_benchmark_side_is_total_return(benchmark_env):
    _value, breakdown = portfolio_utils.compute_tracking_error("alice", "BENCH.L", include_breakdown=True)

    first = breakdown["active_returns"][0]
    assert first["benchmark_return"] == pytest.approx(0.0)  # ex-date: dividend offsets the drop
    assert breakdown["benchmark_return_basis"] == tr.TOTAL_RETURN_BASIS


# ───────────────────── alpha / tracking error: portfolio side (#9571) ─────────────────────

FLAT = [100.0] * len(DATES)


@pytest.fixture
def portfolio_env(monkeypatch):
    """An owner whose holdings are set per test, priced from ``closes`` (default CLOSES)."""
    state = {"holdings": [], "closes": {"FLATB": FLAT}}  # FLATB: benchmark with no actions file

    def fake_build(owner, accounts_root=None, pricing_date=None):
        return {"accounts": [{"holdings": state["holdings"]}]}

    def fake_meta(ticker, exchange, days):
        return pd.DataFrame({"Date": DATES, "Close": state["closes"].get(ticker, CLOSES)})

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build)
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda t, latest: (t.split(".")[0], "L"))
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_meta)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    return state


def _alpha_breakdown(benchmark: str = "FLATB.L") -> dict:
    _value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", benchmark, days=5, include_breakdown=True)
    return breakdown


def test_alpha_portfolio_side_is_total_return(store, portfolio_env):
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [{"ticker": "PAY", "exchange": "L", "units": 2}]

    value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", "FLATB.L", days=5, include_breakdown=True)

    # Price alone is 100 -> 100 (0%); reinvesting the 2.00 dividend gives 100/98 - 1.
    assert breakdown["portfolio_cumulative_return"] == pytest.approx(TOTAL_LEVELS[-1] / 100.0 - 1.0)
    assert value == pytest.approx(TOTAL_LEVELS[-1] / 100.0 - 1.0)
    assert breakdown["portfolio_return_basis"] == tr.TOTAL_RETURN_BASIS
    assert breakdown["portfolio_price_basis_share"] == pytest.approx(0.0)


def test_tracking_error_portfolio_side_is_total_return(store, portfolio_env):
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [{"ticker": "PAY", "exchange": "L", "units": 2}]

    _value, breakdown = portfolio_utils.compute_tracking_error("alice", "FLATB.L", days=5, include_breakdown=True)

    first = breakdown["active_returns"][0]
    assert first["portfolio_return"] == pytest.approx(0.0)  # ex-date: dividend offsets the 2.00 drop
    assert breakdown["portfolio_return_basis"] == tr.TOTAL_RETURN_BASIS


def test_portfolio_basis_mixed_reports_price_share(store, portfolio_env):
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [
        {"ticker": "PAY", "exchange": "L", "units": 3},
        {"ticker": "NOFILE", "exchange": "L", "units": 1},
    ]

    breakdown = _alpha_breakdown()

    assert breakdown["portfolio_return_basis"] == tr.MIXED_RETURN_BASIS
    pay_last = 3 * TOTAL_LEVELS[-1]
    nofile_last = 1 * CLOSES[-1]
    assert breakdown["portfolio_price_basis_share"] == pytest.approx(nofile_last / (pay_last + nofile_last))
    # Each holding on its own basis: PAY reinvested, NOFILE at price.
    expected = (pay_last + nofile_last) / (3 * CLOSES[0] + 1 * CLOSES[0]) - 1.0
    assert breakdown["portfolio_cumulative_return"] == pytest.approx(expected)


def test_portfolio_without_any_actions_is_price(store, portfolio_env):
    portfolio_env["holdings"] = [{"ticker": "NOFILE", "exchange": "L", "units": 1}]

    breakdown = _alpha_breakdown()

    assert breakdown["portfolio_return_basis"] == tr.PRICE_RETURN_BASIS
    assert breakdown["portfolio_price_basis_share"] == pytest.approx(1.0)
    assert breakdown["portfolio_cumulative_return"] == pytest.approx(0.0)


UNPRICEABLE = [float("nan")] * len(DATES)  # all-NaN closes: ``_holding_closes`` returns None


def test_unpriced_price_only_holding_makes_basis_mixed(store, portfolio_env):
    """A price-only holding dropped for want of closes is not hidden behind a "total" label (#9606)."""
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [
        {"ticker": "PAY", "exchange": "L", "units": 2},
        {"ticker": "NOFILE", "exchange": "L", "units": 1},
    ]
    portfolio_env["closes"]["NOFILE"] = UNPRICEABLE

    breakdown = _alpha_breakdown()

    assert breakdown["portfolio_return_basis"] == tr.MIXED_RETURN_BASIS
    # The unpriced holding has no value to weight: the share covers the priced holdings.
    assert breakdown["portfolio_price_basis_share"] == pytest.approx(0.0)
    assert breakdown["portfolio_unpriced_holdings"] == [{"ticker": "NOFILE.L", "return_basis": tr.PRICE_RETURN_BASIS}]


def test_unpriced_holding_with_actions_counts_as_total(store, portfolio_env):
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [
        {"ticker": "PAY", "exchange": "L", "units": 2},
        {"ticker": "NOFILE", "exchange": "L", "units": 1},
    ]
    portfolio_env["closes"]["PAY"] = UNPRICEABLE

    breakdown = _alpha_breakdown()

    assert breakdown["portfolio_return_basis"] == tr.MIXED_RETURN_BASIS
    assert breakdown["portfolio_price_basis_share"] == pytest.approx(1.0)
    assert breakdown["portfolio_unpriced_holdings"] == [{"ticker": "PAY.L", "return_basis": tr.TOTAL_RETURN_BASIS}]


def test_fully_priced_portfolio_lists_no_unpriced_holdings(store, portfolio_env):
    portfolio_env["holdings"] = [{"ticker": "NOFILE", "exchange": "L", "units": 1}]

    assert _alpha_breakdown()["portfolio_unpriced_holdings"] == []


def test_ledger_dividend_cash_is_not_double_counted(store, portfolio_env, monkeypatch):
    """The dividend is booked in the ledger and sits in the current cash balance; it still counts once.

    The alpha series values the current holdings (including the current cash
    balance, which already contains the 4.00 dividend) at historical closes.
    Cash is flat at 1.0, so it adds no return; the only income is the
    reinvested stored dividend. Ledger transactions are not read on this path.
    """
    store("PAY", "L", {EX_DATE: 2.0})
    portfolio_env["holdings"] = [
        {"ticker": "PAY", "exchange": "L", "units": 2},
        {"ticker": "CASH.GBP", "exchange": "GBP", "units": 4.0},
    ]
    portfolio_env["closes"]["CASH"] = [1.0] * len(DATES)
    dividend_tx = {"date": EX_DATE.date().isoformat(), "type": "DIVIDEND", "ticker": "PAY.L", "amount_minor": 400}
    monkeypatch.setattr(portfolio_utils, "load_transactions", lambda owner: [dividend_tx])
    with_ledger = _alpha_breakdown()
    monkeypatch.setattr(portfolio_utils, "load_transactions", lambda owner: [])
    without_ledger = _alpha_breakdown()

    once = (2 * TOTAL_LEVELS[-1] + 4.0) / (2 * CLOSES[0] + 4.0) - 1.0
    twice = (2 * TOTAL_LEVELS[-1] + 4.0 + 4.0) / (2 * CLOSES[0] + 4.0) - 1.0
    assert with_ledger["portfolio_cumulative_return"] == pytest.approx(once)
    assert with_ledger["portfolio_cumulative_return"] != pytest.approx(twice)
    assert with_ledger["portfolio_cumulative_return"] == without_ledger["portfolio_cumulative_return"]
    # Cash is on neither basis: the one security is on total return.
    assert with_ledger["portfolio_return_basis"] == tr.TOTAL_RETURN_BASIS
    assert with_ledger["portfolio_price_basis_share"] == pytest.approx(0.0)


def test_max_drawdown_unchanged_while_alpha_moves(store, portfolio_env):
    portfolio_env["holdings"] = [{"ticker": "PAY", "exchange": "L", "units": 2}]
    store("PAY", "L", {})  # actions file without dividends: total return equals price
    drawdown_before = portfolio_utils.compute_max_drawdown("alice", days=5)
    alpha_before = portfolio_utils.compute_alpha_vs_benchmark("alice", "FLATB.L", days=5)

    store("PAY", "L", BIG_DIVIDEND)

    assert drawdown_before == pytest.approx(98.0 / 100.0 - 1.0)
    assert portfolio_utils.compute_max_drawdown("alice", days=5) == pytest.approx(drawdown_before)
    assert portfolio_utils.compute_alpha_vs_benchmark("alice", "FLATB.L", days=5) > alpha_before


# ───────────────────────────── trading agent ──────────────────────────────


def test_trading_agent_returns_are_total_returns(store):
    store("PAY", "L", {EX_DATE: 2.0})
    tdf = _frame(Ticker="PAY.L")

    returns, basis = trading_agent._daily_returns(tdf, "Close", "PAY.L")

    assert basis == tr.TOTAL_RETURN_BASIS
    assert returns.iloc[0] == pytest.approx(0.0)
    assert trading_agent._daily_returns(tdf, "Close", "PAY")[1] == tr.PRICE_RETURN_BASIS


# ─────────────────────── keep-price consumers (must not change) ───────────────────────

# A dividend this large would swing any total-return figure by 50%.
BIG_DIVIDEND = {EX_DATE: 50.0}


@pytest.fixture
def owner_env(monkeypatch):
    holdings = [{"ticker": "PAY", "exchange": "L", "units": 2}]

    def fake_build(owner, accounts_root=None, pricing_date=None):
        return {"accounts": [{"holdings": holdings}]}

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build)
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda t, latest: (t.split(".")[0], "L"))
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", lambda t, e, d: _frame())
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})


def test_max_drawdown_stays_on_price(store, owner_env):
    store("PAY", "L", BIG_DIVIDEND)

    assert portfolio_utils.compute_max_drawdown("alice", days=5) == pytest.approx(98.0 / 100.0 - 1.0)


def test_owner_performance_stays_on_price(store, owner_env):
    before = portfolio_utils.compute_owner_performance("alice", days=5)
    store("PAY", "L", BIG_DIVIDEND)
    after = portfolio_utils.compute_owner_performance("alice", days=5)

    assert after == before
    assert [row["value"] for row in after["history"]] == pytest.approx([2 * c for c in CLOSES])


def test_ledger_closes_stay_on_price(store, monkeypatch):
    store("PAY", "L", BIG_DIVIDEND)
    monkeypatch.setattr(ledger_performance, "_resolve_symbol", lambda key: ("PAY", "L"))
    monkeypatch.setattr(ts_cache, "load_meta_timeseries_range", lambda *a, **k: _frame())

    closes = ledger_performance.load_gbp_closes("PAY.L", DATES[0].date(), DATES[-1].date())

    assert closes.tolist() == pytest.approx(CLOSES)


def test_price_changes_stay_on_price(store, monkeypatch):
    store("PAY", "L", BIG_DIVIDEND)
    yday = dt.date.today() - dt.timedelta(days=1)

    def fake_range(sym, ex, start_date, end_date, **_kwargs):
        price = 100.0 if start_date == instrument_api._nearest_weekday(yday, forward=False) else 80.0
        return pd.DataFrame({"Date": [pd.Timestamp(start_date)], "Close": [price]})

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda t, latest: ("PAY", "L"))
    monkeypatch.setattr(instrument_api, "is_cache_only", lambda: False)
    monkeypatch.setattr(instrument_api, "load_meta_timeseries_range", fake_range)

    assert instrument_api.price_change_pct("PAY.L", 7) == pytest.approx(25.0)


def test_timeseries_for_ticker_stays_on_price(store, monkeypatch):
    store("PAY", "L", BIG_DIVIDEND)
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda t, latest: ("PAY", "L"))
    monkeypatch.setattr(instrument_api, "has_cached_meta_timeseries", lambda s, e: True)
    monkeypatch.setattr(instrument_api, "load_meta_timeseries_range", lambda *a, **k: _frame())
    monkeypatch.setattr(instrument_api, "get_scaling_override", lambda *a, **k: 1.0)

    payload = instrument_api.timeseries_for_ticker("PAY.L", start_date=DATES[0].date(), end_date=DATES[-1].date())

    assert [row["close"] for row in payload["prices"]] == pytest.approx(CLOSES)


@pytest.mark.parametrize(
    ("ticker", "exchange", "expected"),
    [
        ("CASH", "GBP", True),
        ("GBP", "CASH", True),
        ("cash", "gbp", True),
        ("CASHPLUS", "L", False),
        ("PETROCASH", "L", False),
        ("VWRL", "L", False),
    ],
)
def test_is_cash_holding_matches_whole_ticker_or_exchange_only(ticker, exchange, expected):
    """Only ``CASH.<ccy>`` / ``<ccy>.CASH`` count as cash, never a ticker that merely contains CASH."""
    assert portfolio_utils._is_cash_holding(ticker, exchange) is expected
