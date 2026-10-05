"""Performance/risk consumers on total return; price/valuation consumers pinned to price (#9370)."""

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

    def write(ticker: str, exchange: str, dividends: dict | None = None, *, splits: dict | None = None) -> None:
        rows = [(pd.Timestamp(d), "dividend", v) for d, v in (dividends or {}).items()]
        rows += [(pd.Timestamp(d), "split", v) for d, v in (splits or {}).items()]
        frame = pd.DataFrame(
            [{"Date": d, "Action": a, "Value": v, "Currency": "GBP", "Source": "test"} for d, a, v in rows],
            columns=ACTION_COLUMNS,
        )
        frame["Date"] = frame["Date"].astype("datetime64[ms]")
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

    returns, basis = scenario_tester._forward_returns("PAY", "L", DATES[0].date())

    assert basis == tr.TOTAL_RETURN_BASIS
    # 1 calendar day -> ex-date close: price says -2%, total return says 0%.
    assert returns["1d"] == pytest.approx(0.0)
    assert returns["1w"] is None  # the five-day fixture ends before a week has passed


def test_calc_return_uses_total_return(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader({"PAY": _frame()}))
    _no_scaling(monkeypatch)

    ret = scenario_tester._calc_return("PAY", "L", DATES[0].date(), 4)

    assert ret == pytest.approx(TOTAL_LEVELS[-1] / 100.0 - 1.0)


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
    event = {"date": DATES[0].date(), "proxy_index": "PRX.L"}

    result = scenario_tester.apply_historical_event_portfolio(portfolio, event)

    one_day = result["1d"]
    assert one_day["total_value_gbp"] == pytest.approx(100.0 + 98.0)
    assert one_day["return_basis"] == tr.PRICE_RETURN_BASIS
    assert one_day["price_return_tickers"] == ["NOFILE.L"]


def test_historical_event_portfolio_all_total_return(store, monkeypatch):
    store("PAY", "L", {EX_DATE: 2.0})
    monkeypatch.setattr(scenario_tester, "load_meta_timeseries_range", _range_loader({"PAY": _frame()}))
    _no_scaling(monkeypatch)
    portfolio = {"accounts": [{"holdings": [{"ticker": "PAY.L", "market_value_gbp": 100.0}]}]}

    result = scenario_tester.apply_historical_event_portfolio(portfolio, {"date": DATES[0].date()})

    assert result["1w"]["return_basis"] == tr.TOTAL_RETURN_BASIS
    assert result["1w"]["price_return_tickers"] == []


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


# ───────────────────────────── alpha / tracking error ──────────────────────────────


@pytest.fixture
def benchmark_env(store, monkeypatch):
    store("BENCH", "L", {EX_DATE: 2.0})
    portfolio = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=[d.date() for d in DATES])
    monkeypatch.setattr(portfolio_utils, "_portfolio_value_series", lambda *a, **k: portfolio)
    frames = {"BENCH": _frame(), "NOFILE": _frame()}
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", lambda t, e, d: frames.get(t, pd.DataFrame()).copy())


def test_alpha_benchmark_side_is_total_return(benchmark_env):
    value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", "BENCH.L", include_breakdown=True)

    bench = TOTAL_LEVELS[-1] / 100.0 - 1.0
    assert breakdown["benchmark_cumulative_return"] == pytest.approx(bench)
    assert breakdown["portfolio_cumulative_return"] == pytest.approx(0.04)
    assert value == pytest.approx(0.04 - bench)
    assert breakdown["benchmark_return_basis"] == tr.TOTAL_RETURN_BASIS
    assert breakdown["portfolio_return_basis"] == tr.PRICE_RETURN_BASIS


def test_alpha_benchmark_without_actions_reports_price(benchmark_env):
    _value, breakdown = portfolio_utils.compute_alpha_vs_benchmark("alice", "NOFILE.L", include_breakdown=True)

    assert breakdown["benchmark_cumulative_return"] == pytest.approx(0.0)
    assert breakdown["benchmark_return_basis"] == tr.PRICE_RETURN_BASIS


def test_tracking_error_benchmark_side_is_total_return(benchmark_env):
    _value, breakdown = portfolio_utils.compute_tracking_error("alice", "BENCH.L", include_breakdown=True)

    first = breakdown["active_returns"][0]
    assert first["benchmark_return"] == pytest.approx(0.0)  # ex-date: dividend offsets the drop
    assert breakdown["benchmark_return_basis"] == tr.TOTAL_RETURN_BASIS


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
