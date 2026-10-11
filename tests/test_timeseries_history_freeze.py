"""Declared freeze on curated stored history (#10645).

ESIH.L's first four Yahoo closes look like EUR and were dropped from the
stored parquet (allotmint-data#78); JEGI.L's closes and dividends were
restated in the store (allotmint-data#72, #81). Without a freeze, a live
refetch re-adds the dropped rows (the rolling cache fetches any range before
the cache's first date) and overwrites restated ones (a fetched row whose
values differ wins). A ``history_freeze`` block stops provider data before
its date from ever being fetched or merged; an instrument without it is
fetched exactly as before.
"""

import importlib
import logging
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from backend.timeseries import fetch_yahoo_timeseries as fy
from backend.timeseries import history_freeze as hf
from backend.timeseries import price_adjustments as pa
from backend.timeseries.corporate_actions import CONFIRMED_FROM

BLOCK = {"before": "2020-11-23", "rationale": "first closes look like EUR", "reviewed": "2026-10-11"}


@pytest.fixture
def declare(monkeypatch):
    """Serve ``history_freeze`` metadata for chosen tickers and none for anything else."""
    metas: dict[str, dict] = {}
    monkeypatch.setattr(hf, "get_instrument_meta", lambda ticker: metas.get(ticker, {}))
    monkeypatch.setattr(pa, "get_instrument_meta", lambda ticker: {})

    def _declare(block, ticker="FRZ.L"):
        metas[ticker] = {"history_freeze": block}

    return _declare


def _frame(days, closes):
    n = len(days)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(list(days)),
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1000] * n,
            "Ticker": ["FRZ"] * n,
            "Source": ["Yahoo"] * n,
        }
    )


# ──────────────────────────── validation ────────────────────────────


def test_valid_block_parses():
    freeze = hf.parse_history_freeze({"history_freeze": BLOCK})
    assert freeze == hf.HistoryFreeze(date(2020, 11, 23), "first closes look like EUR", date(2026, 10, 11))


def test_absent_block_is_valid_and_none():
    assert hf.validate_history_freeze({}) == []
    assert hf.parse_history_freeze(None) is None


@pytest.mark.parametrize(
    "block,fragment",
    [
        ({**BLOCK, "before": "23/11/2020"}, "before"),
        ({**BLOCK, "rationale": "  "}, "rationale is required"),
        ({k: v for k, v in BLOCK.items() if k != "reviewed"}, "reviewed"),
        (["2020-11-23"], "must be a JSON object"),
    ],
)
def test_invalid_blocks_are_reported(block, fragment):
    problems = hf.validate_history_freeze({"history_freeze": block})
    assert any(fragment in p for p in problems)
    with pytest.raises(ValueError):
        hf.parse_history_freeze({"history_freeze": block})


def test_invalid_block_is_ignored_with_a_warning(declare, caplog):
    declare({**BLOCK, "before": "soon"})
    with caplog.at_level(logging.WARNING, logger=hf.logger.name):
        assert hf.freeze_date_for("FRZ", "L") is None
    assert "Ignoring invalid history_freeze for FRZ.L" in caplog.text


def test_freeze_date_for_reads_the_declared_date(declare):
    declare(BLOCK)
    assert hf.freeze_date_for("FRZ", "L") == date(2020, 11, 23)
    assert hf.freeze_date_for("OTHER", "L") is None


def test_ticker_the_metadata_lookup_rejects_counts_as_unfrozen(monkeypatch):
    """``get_instrument_meta`` raises for dotted tickers such as ``BRK.B``; that must not block a fetch."""

    def reject(_ticker):
        raise ValueError("invalid ticker or exchange")

    monkeypatch.setattr(hf, "get_instrument_meta", reject)
    assert hf.freeze_date_for("BRK.B", "US") is None


# ──────────────────────────── row filter ────────────────────────────


def test_rows_before_the_freeze_are_dropped_and_attrs_kept():
    df = _frame(["2020-11-20", "2020-11-23", "2020-11-24"], [4.93, 4.36, 4.32])
    df.attrs = {"k": "v"}
    out = hf.drop_frozen_rows(df, date(2020, 11, 23))
    assert out["Date"].dt.date.tolist() == [date(2020, 11, 23), date(2020, 11, 24)]
    assert out.attrs == {"k": "v"}
    assert len(df) == 3  # input untouched


def test_nothing_to_drop_returns_the_same_object():
    df = _frame(["2020-11-23"], [4.36])
    assert hf.drop_frozen_rows(df, date(2020, 11, 23)) is df
    assert hf.drop_frozen_rows(df, None) is df


def test_tz_aware_dates_compare_on_their_calendar_day():
    df = _frame(["2020-11-22", "2020-11-23"], [1.0, 2.0])
    df["Date"] = df["Date"].dt.tz_localize("Europe/London")
    assert hf.drop_frozen_rows(df, date(2020, 11, 23))["Close"].tolist() == [2.0]


# ──────────────────────────── rolling cache ────────────────────────────


def _import_cache():
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


@pytest.fixture
def live_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = _import_cache()
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    return cache


def _window_end(cache) -> date:
    """The last day the rolling cache wants (yesterday, moved back to a weekday)."""
    return cache._weekday_range(datetime.today().date() - timedelta(days=1), 1)[1]


def _recording_fetch(cache, monkeypatch, provider: pd.DataFrame) -> list[dict]:
    """Patch the meta fetcher to serve ``provider`` rows in the window and record each call."""
    calls: list[dict] = []

    def fetch(**kwargs):
        calls.append(kwargs)
        days = provider["Date"].dt.date
        return provider[(days >= kwargs["start_date"]) & (days <= kwargs["end_date"])].reset_index(drop=True)

    monkeypatch.setattr(cache, "fetch_meta_timeseries", fetch)
    return calls


def _bdays(start: date, end: date) -> list[date]:
    return [d.date() for d in pd.bdate_range(start, end)]


def test_dropped_rows_before_the_freeze_are_never_refetched(live_cache, declare, monkeypatch):
    """ESIH.L: the store starts at the freeze date; a long window must not re-add the dropped rows."""
    cache = live_cache
    end = _window_end(cache)
    freeze = (pd.Timestamp(end) - pd.offsets.BDay(20)).date()
    declare({**BLOCK, "before": freeze.isoformat()})
    provider_days = _bdays(freeze - timedelta(days=10), end)
    provider = _frame(provider_days, [4.93 if d < freeze else 4.36 for d in provider_days])
    path = cache.meta_timeseries_cache_path("FRZ", "L")
    stored = provider[(provider["Date"].dt.date >= freeze) & (provider["Date"].dt.date < end)]
    cache._save_parquet(stored.reset_index(drop=True), path)
    calls = _recording_fetch(cache, monkeypatch, provider)

    served = cache.load_meta_timeseries("FRZ", "L", (end - provider_days[0]).days + 30)

    assert calls, "the missing tail after the store should still be fetched"
    assert all(call["start_date"] >= freeze for call in calls)
    assert served["Date"].dt.date.min() == freeze
    assert cache._load_parquet(path)["Date"].dt.date.min() == freeze


def test_fetched_rows_before_the_freeze_never_replace_curated_rows(live_cache, declare, monkeypatch):
    """JEGI.L: restated stored rows must survive a refetch whose overlap reaches before the freeze."""
    cache = live_cache
    end = _window_end(cache)
    freeze = (pd.Timestamp(end) - pd.offsets.BDay(3)).date()
    declare({**BLOCK, "before": freeze.isoformat()})
    days = _bdays(end - timedelta(days=40), end)
    curated = _frame([d for d in days if d < end], [44.0] * (len(days) - 1))
    raw = _frame(days, [177.0 if d < freeze else 44.0 for d in days])
    path = cache.meta_timeseries_cache_path("FRZ", "L")
    cache._save_parquet(curated, path)
    calls = _recording_fetch(cache, monkeypatch, raw)

    cache.load_meta_timeseries("FRZ", "L", 30)

    assert calls and calls[0]["start_date"] < freeze  # the overlap window does reach back
    stored = cache._load_parquet(path)
    assert stored.loc[stored["Date"].dt.date < freeze, "Close"].tolist() == [44.0] * sum(d < freeze for d in days)
    assert stored["Date"].dt.date.max() == end


def test_instrument_without_the_block_still_fetches_the_earlier_chunk(live_cache, declare, monkeypatch):
    cache = live_cache
    end = _window_end(cache)
    first_stored = (pd.Timestamp(end) - pd.offsets.BDay(20)).date()
    provider_days = _bdays(first_stored - timedelta(days=10), end)
    provider = _frame(provider_days, [1.0] * len(provider_days))
    path = cache.meta_timeseries_cache_path("FRZ", "L")
    cache._save_parquet(provider[provider["Date"].dt.date >= first_stored].reset_index(drop=True), path)
    calls = _recording_fetch(cache, monkeypatch, provider)

    served = cache.load_meta_timeseries("FRZ", "L", (end - provider_days[0]).days + 1)

    assert any(call["start_date"] < first_stored for call in calls)
    assert served["Date"].dt.date.min() < first_stored


# ──────────────────────────── corporate actions ────────────────────────────


def _actions(days, confirmed_from):
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(days).astype("datetime64[ms]"),
            "Action": ["dividend"] * len(days),
            "Value": [1.0] * len(days),
            "Currency": ["GBp"] * len(days),
            "Source": ["Yahoo"] * len(days),
        }
    )
    frame.attrs = {CONFIRMED_FROM: confirmed_from}
    return frame


def test_fetched_actions_before_the_freeze_are_dropped_and_confirmation_clamped(declare):
    declare({**BLOCK, "before": "2022-02-04"})
    actions = _actions(["2021-09-09", "2022-02-24"], "2007-01-01")

    kept = fy._without_frozen_actions("FRZ", "L", actions)

    assert kept["Date"].dt.date.tolist() == [date(2022, 2, 24)]
    assert kept.attrs[CONFIRMED_FROM] == "2022-02-04"
    assert actions.attrs[CONFIRMED_FROM] == "2007-01-01"  # caller's frame untouched


def test_actions_without_a_freeze_are_returned_as_fetched(declare):
    actions = _actions(["2021-09-09"], "2007-01-01")
    assert fy._without_frozen_actions("FRZ", "L", actions) is actions


def test_frozen_actions_are_never_recorded(declare, monkeypatch):
    declare({**BLOCK, "before": "2022-02-04"})
    recorded: list[pd.DataFrame] = []
    monkeypatch.setattr(fy, "record_corporate_actions", lambda sym, exch, frame: recorded.append(frame))

    fy._store_actions("FRZ.L", "L", _actions(["2021-09-09", "2022-02-24"], "2021-01-01"))

    assert [d.date() for d in recorded[0]["Date"]] == [date(2022, 2, 24)]
