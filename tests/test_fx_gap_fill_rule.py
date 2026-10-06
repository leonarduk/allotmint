"""One FX gap-fill rule for historical GBP prices (#9759).

The timeseries loader's ``Close_gbp`` (behind ``ledger_performance``) and the
#9671 value series (``portfolio_utils._gbp_rates``) both align stored FX rates
to price dates with ``cache.align_fx_rates``: the latest rate at most
``_MAX_FX_GAP_FILL_DAYS`` before the date, never a later one. A date without
one has no GBP price, and is never priced at its native (unconverted) close.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backend import report_periodic
from backend.common import instrument_api
from backend.common import ledger_performance as lp
from backend.common import portfolio_utils as pu
from backend.timeseries import cache

JAN = [d.date() for d in pd.bdate_range("2024-01-01", "2024-01-31")]
# Rates on 1-5 Jan and from 16 Jan: a 10-day gap. 8-10 Jan are within five
# days of the 5 Jan rate; 11, 12 and 15 Jan are not.
RATES = {day: 0.8 for day in JAN if day <= dt.date(2024, 1, 5) or day >= dt.date(2024, 1, 16)}
GAP_DAYS = [dt.date(2024, 1, 11), dt.date(2024, 1, 12), dt.date(2024, 1, 15)]


def _fx(rates: dict[dt.date, float]) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime(list(rates)), "Rate": list(rates.values())})


def _closes_frame(days: list[dt.date], close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(days),
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": 1000,
            "Ticker": "USCO",
            "Source": "test",
        }
    )


# ──────────────────────────────────────────────────────────────
# The helper
# ──────────────────────────────────────────────────────────────
def test_align_takes_the_latest_rate_within_the_window_and_never_a_later_one() -> None:
    fx = _fx({dt.date(2024, 1, 5): 0.8, dt.date(2024, 1, 20): 0.9})
    days = pd.Index([dt.date(2024, 1, 4), dt.date(2024, 1, 5), dt.date(2024, 1, 10), dt.date(2024, 1, 11)])

    rates = cache.align_fx_rates(fx, days)

    assert list(rates.index) == list(days)
    assert pd.isna(rates.iloc[0])  # before the first rate: no backfill
    assert rates.iloc[1:3].tolist() == [0.8, 0.8]  # same day, exactly five days on
    assert pd.isna(rates.iloc[3])  # six days on


def test_align_keeps_the_last_row_of_a_duplicated_date_and_ignores_nan_rates() -> None:
    fx = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-03", "2024-01-02", "2024-01-03", "2024-01-04"]),
            "Rate": [0.7, 0.6, 0.75, float("nan")],
        }
    )

    rates = cache.align_fx_rates(fx, pd.Index([dt.date(2024, 1, 4), dt.date(2024, 1, 2)]))

    assert rates.tolist() == [0.75, 0.6]


def test_align_with_no_rates_is_all_nan() -> None:
    rates = cache.align_fx_rates(pd.DataFrame(columns=["Date", "Rate"]), pd.Index([dt.date(2024, 1, 2)]))

    assert rates.isna().all()


def test_series_path_uses_the_shared_helper_and_window() -> None:
    assert pu._MAX_FX_GAP_FILL_DAYS is cache._MAX_FX_GAP_FILL_DAYS
    assert pu.align_fx_rates is cache.align_fx_rates


# ──────────────────────────────────────────────────────────────
# The timeseries loader's Close_gbp (live and offline paths)
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def usd_loader(monkeypatch: pytest.MonkeyPatch):
    """``load_meta_timeseries_range`` for a USD instrument over January, with live FX from ``RATES``."""
    calls: list[tuple[dt.date, dt.date]] = []

    def fake_fx(base, quote, start, end):
        calls.append((start, end))
        days = [day for day in RATES if start <= day <= end]
        return pd.DataFrame({"Date": days, "Rate": [RATES[day] for day in days]})

    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(JAN))
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": "USD"})
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    return calls


def test_live_loader_does_not_apply_a_rate_more_than_five_days_old(usd_loader) -> None:
    df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[-1])

    by_day = dict(zip(df["Date"].dt.date, df["Close_gbp"]))
    assert [day for day, value in by_day.items() if pd.isna(value)] == GAP_DAYS
    assert by_day[dt.date(2024, 1, 10)] == pytest.approx(80.0)  # exactly five days old
    assert df["Close"].tolist() == [100.0] * len(JAN)


def test_live_loader_does_not_backfill_before_the_first_rate(monkeypatch: pytest.MonkeyPatch, usd_loader) -> None:
    monkeypatch.setitem(RATES, dt.date(2024, 1, 1), 0.8)
    for day in [d for d in RATES if d < dt.date(2024, 1, 16)]:
        monkeypatch.delitem(RATES, day)

    df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[-1])

    by_day = dict(zip(df["Date"].dt.date, df["Close_gbp"]))
    assert all(pd.isna(by_day[day]) for day in JAN if day < dt.date(2024, 1, 16))
    assert by_day[dt.date(2024, 1, 16)] == pytest.approx(80.0)


def test_live_fx_window_reaches_back_the_gap_window(usd_loader) -> None:
    """The first price date can take the last rate before it, as the cache-only path can."""
    cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[-1])

    assert usd_loader[0] == (JAN[0] - dt.timedelta(days=cache._MAX_FX_GAP_FILL_DAYS), JAN[-1])


def test_offline_loader_applies_the_same_window(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(JAN))
    monkeypatch.setattr(cache, "OFFLINE_MODE", True)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": "USD"})
    path = tmp_path / "fx" / "USD.parquet"
    path.parent.mkdir(parents=True)
    _fx(RATES).to_parquet(path, index=False)

    df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[-1])

    missing = [day for day, value in zip(df["Date"].dt.date, df["Close_gbp"]) if pd.isna(value)]
    assert missing == GAP_DAYS


# ──────────────────────────────────────────────────────────────
# Ledger closes and the #9671 series agree (cache-only, the page path)
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def cached_usd(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """A USD instrument with January closes and the ``RATES`` history in the FX cache."""
    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(JAN))
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": "USD"})
    monkeypatch.setattr(cache.refresh_queue, "enqueue", lambda *_args: False)
    monkeypatch.setattr(cache.refresh_queue, "enqueue_fx", lambda *_args: False)
    monkeypatch.setattr(pu, "get_scaling_override", lambda *_args: 1.0)
    monkeypatch.setattr(lp, "_resolve_symbol", lambda key: tuple(key.split(".", 1)))
    path = tmp_path / "fx" / "USD.parquet"
    path.parent.mkdir(parents=True)
    _fx(RATES).to_parquet(path, index=False)


def test_ledger_closes_and_series_closes_agree_date_for_date_over_a_ten_day_fx_gap(cached_usd) -> None:
    with cache.cache_only():
        ledger = lp.load_gbp_closes("USCO.N", JAN[0], JAN[-1])
        native = pd.Series(100.0, index=JAN)
        series, currency, missing = pu._closes_in_gbp(native, "USCO", "N")

    assert currency == "USD"
    assert list(missing) == GAP_DAYS
    assert [ts.date() for ts in ledger.index] == list(series.index)
    assert ledger.to_numpy() == pytest.approx(series.to_numpy())
    assert not set(GAP_DAYS) & {ts.date() for ts in ledger.index}
    entry = ledger.attrs[lp.UNCONVERTED_ATTR]
    assert entry["reason"] == pu.FX_MISSING_SOME_DATES
    assert entry["missing_fx_days"] == len(GAP_DAYS)
    assert (entry["first"], entry["last"]) == ("2024-01-11", "2024-01-15")


@pytest.mark.parametrize(
    "window",
    [
        (dt.date(2024, 3, 1), dt.date(2024, 3, 5)),  # FX cache stale by more than the gap window
        (dt.date(2023, 6, 1), dt.date(2023, 6, 5)),  # before the stored history starts
    ],
)
def test_cache_only_window_with_no_qualifying_rate_gets_nan_close_gbp_not_no_column(
    cached_usd, monkeypatch: pytest.MonkeyPatch, window
) -> None:
    """No column would mean "never converted", which readers answer with the native close (#7722)."""
    start, end = window
    days = [d.date() for d in pd.bdate_range(start, end)]
    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(days))
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(cache.refresh_queue, "enqueue", lambda ticker, exchange: queued.append((ticker, exchange)))

    with cache.cache_only():
        df = cache.load_meta_timeseries_range("USCO", "N", start, end)

    assert "Close_gbp" in df.columns
    assert df["Close_gbp"].isna().all()
    assert df["Close"].tolist() == [100.0] * len(days)
    if start > JAN[-1]:
        assert queued == [("USCO", "N")]  # the stale FX cache is still queued for a refresh


@pytest.mark.parametrize("cache_only", [False, True])
def test_no_rate_at_all_leaves_no_close_gbp_on_the_live_and_cache_only_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path, cache_only: bool
) -> None:
    """The live path is empty only when the pair has no rate and no constant; cache-only agrees (#9664).

    A live fetch covers its own window, so it can't be "stale": a failed fetch
    falls back to the constant, and only a pair with no constant comes back
    empty. With no FX file and no constant, the cache-only path ends up in the
    same place, so neither path adds a ``Close_gbp`` column.
    """
    from backend.utils import fx_rates

    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(JAN[:5]))
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": "USD"})
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache.refresh_queue, "enqueue", lambda *_args: False)
    monkeypatch.setattr(fx_rates, "FALLBACK_RATES", {})
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", lambda *_args: pd.DataFrame(columns=["Date", "Rate"]))
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fx_rates.fetch_fx_rate_range)
    fx_rates.fetch_fx_rate_range.cache_clear()

    if cache_only:
        with cache.cache_only():
            df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[4])
    else:
        df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[4])

    assert "Close_gbp" not in df.columns
    assert df["Close"].tolist() == [100.0] * 5


def test_cross_currency_gap_in_the_base_leg_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD prices in EUR: a date without a EUR rate in the window has no Close_eur."""
    eur = {day: 0.9 for day in JAN if day <= dt.date(2024, 1, 5)}

    def fake_fx(base, quote, start, end):
        rates = RATES if base == "USD" else eur
        days = [day for day in rates if start <= day <= end]
        return pd.DataFrame({"Date": days, "Rate": [rates[day] for day in days]})

    monkeypatch.setattr(cache, "_memoized_range", lambda *_args: _closes_frame(JAN[:10]))
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": "USD"})
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)

    df = cache.load_meta_timeseries_range("USCO", "N", JAN[0], JAN[9], base_currency="EUR")

    by_day = dict(zip(df["Date"].dt.date, df["Close_eur"]))
    assert by_day[dt.date(2024, 1, 10)] == pytest.approx(100.0 * 0.8 / 0.9)
    assert pd.isna(by_day[dt.date(2024, 1, 11)])  # EUR rate six days old


# ──────────────────────────────────────────────────────────────
# load_gbp_closes never falls back to the native close (#7722)
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def loader_frame(monkeypatch: pytest.MonkeyPatch):
    """Serve ``frame["df"]`` from the timeseries loader, with ``frame["currency"]`` as the instrument's."""
    frame: dict = {"currency": "USD"}
    monkeypatch.setattr(lp, "_resolve_symbol", lambda key: tuple(key.split(".", 1)))
    monkeypatch.setattr(cache, "load_meta_timeseries_range", lambda *_a, **_k: frame["df"])
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: {"currency": frame["currency"]})
    return frame


def test_nan_close_gbp_is_a_missing_price_not_the_native_close(loader_frame) -> None:
    df = _closes_frame(JAN[:3])
    df["Close_gbp"] = [80.0, float("nan"), 82.0]
    loader_frame["df"] = df

    closes = lp.load_gbp_closes("USCO.N", JAN[0], JAN[2])

    assert closes.to_dict() == {pd.Timestamp(JAN[0]): 80.0, pd.Timestamp(JAN[2]): 82.0}
    assert closes.attrs[lp.UNCONVERTED_ATTR]["missing_fx_days"] == 1


def test_unconverted_non_gbp_frame_has_no_closes(loader_frame) -> None:
    """No Close_gbp column at all (no rate, #9664): native USD closes are not GBP closes."""
    loader_frame["df"] = _closes_frame(JAN[:3])

    closes = lp.load_gbp_closes("USCO.N", JAN[0], JAN[2])

    assert closes.empty
    entry = closes.attrs[lp.UNCONVERTED_ATTR]
    assert (entry["reason"], entry["missing_fx_days"], entry["currency"]) == (pu.FX_MISSING_ALL_DATES, 3, "USD")


@pytest.mark.parametrize("currency", ["GBP", "GBX"])
def test_sterling_frame_without_close_gbp_uses_the_scaled_native_close(
    loader_frame, monkeypatch: pytest.MonkeyPatch, currency: str
) -> None:
    loader_frame["currency"] = currency
    loader_frame["df"] = _closes_frame(JAN[:2], close=250.0)
    import backend.utils.timeseries_helpers as helpers

    monkeypatch.setattr(helpers, "get_scaling_override", lambda *_args: 0.01 if currency == "GBX" else 1.0)

    closes = lp.load_gbp_closes("ABC.L", JAN[0], JAN[1])

    assert closes.tolist() == ([2.5, 2.5] if currency == "GBX" else [250.0, 250.0])
    assert lp.UNCONVERTED_ATTR not in closes.attrs


# ──────────────────────────────────────────────────────────────
# Surfacing: ledger performance and the report's coverage note
# ──────────────────────────────────────────────────────────────
TRANSACTIONS = [
    {"date": "2024-01-02", "type": "DEPOSIT", "amount_minor": 100000},
    {"date": "2024-01-02", "type": "BUY", "ticker": "USCO.N", "units": 10, "amount_minor": 80000},
    {"date": "2024-01-02", "type": "BUY", "ticker": "JPCO.T", "units": 1, "amount_minor": 10000},
]


def _loader_with_gaps(key: str, start: dt.date, end: dt.date) -> pd.Series:
    if key == "USCO.N":
        closes = pd.Series(80.0, index=pd.DatetimeIndex([pd.Timestamp(d) for d in JAN if d not in GAP_DAYS]))
        closes.attrs[lp.UNCONVERTED_ATTR] = {"ticker": key, "reason": pu.FX_MISSING_SOME_DATES}
        return closes
    closes = pd.Series(dtype=float)
    closes.attrs[lp.UNCONVERTED_ATTR] = {"ticker": key, "reason": pu.FX_MISSING_ALL_DATES}
    return closes


def test_ledger_performance_lists_instruments_with_fx_gaps() -> None:
    ledger = lp.AccountLedger("isa", TRANSACTIONS, True)

    perf = lp.build_ledger_performance([ledger], JAN[-1], price_loader=_loader_with_gaps)

    assert perf is not None
    assert perf.unpriced == ("JPCO.T",)  # nothing convertible: valued at its trade price
    assert [entry["ticker"] for entry in perf.unconverted] == ["JPCO.T", "USCO.N"]
    # The gap days carry the last converted close, like any missing price.
    assert perf.instrument_values.loc[pd.Timestamp(GAP_DAYS[0]), "USCO.N"] == pytest.approx(800.0)


def test_report_coverage_note_names_partly_converted_instruments() -> None:
    inputs = report_periodic.InsightInputs(unpriced=("JPCO.T",), fx_gaps=("USCO.N",))

    note = report_periodic.rule_data_coverage(inputs)

    assert note is not None
    assert "valued at trade prices" in note
    assert "no FX rate on some dates (USCO.N)" in note


def test_instrument_mini_series_skips_rows_without_a_gbp_close(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _closes_frame(JAN[:3])
    df["Close_gbp"] = [80.0, float("nan"), 82.0]
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda ticker, _prices: ("USCO", "N"))
    monkeypatch.setattr(instrument_api, "has_cached_meta_timeseries", lambda *_args: True)
    monkeypatch.setattr(instrument_api, "load_meta_timeseries_range", lambda *_a, **_k: df)
    monkeypatch.setattr(instrument_api, "get_scaling_override", lambda *_args: 1.0)

    payload = instrument_api.timeseries_for_ticker("USCO.N", start_date=JAN[0], end_date=JAN[2])

    rows = payload["mini"]["30"]
    assert [row["close_gbp"] for row in rows] == [80.0, 82.0]
