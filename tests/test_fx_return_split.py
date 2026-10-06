"""Local vs FX split of a non-sterling instrument's GBP price return (#9776, #9686 phase 3).

``local_fx_return_split`` reads native closes and stored FX rates only. These
tests pin the arithmetic (the components sum to the GBP return), reconciliation
with the ``Close_gbp`` the cache-only loader produces for the same dates, no
split when an endpoint has no usable rate, and no split for GBP/GBX.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.utils.fx_rates as fx_rates
from backend.app import create_app
from backend.common import fx_return_split as split_mod
from backend.common import portfolio_utils as pu
from backend.common.fx_return_split import local_fx_return_split
from backend.config import config
from backend.timeseries import cache

START, END = date(2024, 3, 1), date(2024, 3, 28)


def _closes(days: list[date], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime(days), "Close": closes})


def _rates(rates: dict[date, float]) -> pd.DataFrame:
    return pd.DataFrame({"Date": pd.to_datetime(list(rates)), "Rate": list(rates.values())})


@pytest.fixture
def usd_meta(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Both currency resolvers see ``meta["currency"]`` for every instrument; scaling is 1."""
    meta = {"currency": "USD"}
    monkeypatch.setattr(pu, "get_instrument_meta", lambda _t: dict(meta))
    monkeypatch.setattr(pu, "get_security_meta", lambda _t: dict(meta))
    monkeypatch.setattr(pu, "instrument_currency", lambda _t, _e: meta["currency"])
    monkeypatch.setattr(cache, "get_instrument_meta", lambda _t: dict(meta))
    monkeypatch.setattr(split_mod, "get_scaling_override", lambda *_args: 1.0)
    return meta


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch, usd_meta) -> dict[str, pd.DataFrame]:
    """Stub the stored closes and FX history; tests set ``closes`` and ``fx``."""
    state = {
        "closes": _closes([START, END], [100.0, 110.0]),
        "fx": _rates({START: 0.80, END: 0.76}),
    }
    monkeypatch.setattr(split_mod, "load_meta_timeseries_range", lambda *_a, **_k: state["closes"])
    monkeypatch.setattr(pu, "load_fx_history", lambda *_a, **_k: state["fx"])
    return state


def test_usd_up_ten_percent_with_usd_down_five_percent_splits_exactly(stored) -> None:
    """The issue's worked example: +10% local, -5% FX, -0.5% cross, +4.5% GBP."""
    result = local_fx_return_split("USCO", "N", START, END)

    assert result["applicable"] is True
    assert result["reason"] is None
    assert result["basis"] == "price"
    assert result["currency"] == "USD"
    assert (result["start"], result["end"]) == (START.isoformat(), END.isoformat())
    assert (result["start_rate"], result["end_rate"]) == (pytest.approx(0.80), pytest.approx(0.76))
    assert result["local_return"] == pytest.approx(0.10)
    assert result["fx_return"] == pytest.approx(-0.05)
    assert result["cross_term"] == pytest.approx(-0.005)
    assert result["gbp_return"] == pytest.approx(0.045)
    parts = result["local_return"] + result["fx_return"] + result["cross_term"]
    assert parts == pytest.approx(result["gbp_return"], abs=1e-15)
    assert [round(100 * result[k], 2) for k in ("local_return", "fx_return", "cross_term", "gbp_return")] == [
        10.0,
        -5.0,
        -0.5,
        4.5,
    ]


def test_endpoints_are_the_first_and_last_closes_and_use_a_rate_within_the_fill_window(stored) -> None:
    """Weekend endpoints take Friday's rate (within ``_MAX_FX_GAP_FILL_DAYS``)."""
    days = [date(2024, 3, 2), date(2024, 3, 10), date(2024, 3, 17)]  # Sat, Sun, Sun
    stored["closes"] = _closes(days, [50.0, 999.0, 60.0])
    stored["fx"] = _rates({date(2024, 3, 1): 0.8, date(2024, 3, 15): 0.88})

    result = local_fx_return_split("USCO", "N", START, END)

    assert (result["start"], result["end"]) == ("2024-03-02", "2024-03-17")
    assert result["local_return"] == pytest.approx(0.2)
    assert result["fx_return"] == pytest.approx(0.1)
    assert result["gbp_return"] == pytest.approx(1.2 * 1.1 - 1)


@pytest.mark.parametrize(
    ("fx", "start_rate", "end_rate"),
    [
        pytest.param({END: 0.76}, None, 0.76, id="no-rate-at-start"),
        pytest.param({START: 0.80}, 0.80, None, id="last-rate-beyond-the-fill-window-at-end"),
        pytest.param({START - timedelta(days=6): 0.80, END: 0.76}, None, 0.76, id="start-rate-six-days-old"),
        pytest.param({}, None, None, id="no-stored-history-not-the-fallback-constant"),
    ],
)
def test_missing_fx_rate_at_either_endpoint_gives_no_split(stored, fx, start_rate, end_rate) -> None:
    stored["fx"] = _rates(fx) if fx else pd.DataFrame(columns=["Date", "Rate"])

    result = local_fx_return_split("USCO", "N", START, END)

    assert result["applicable"] is True
    assert result["reason"] == "missing_fx_rate"
    assert (result["start_rate"], result["end_rate"]) == (start_rate, end_rate)
    for key in ("local_return", "fx_return", "cross_term", "gbp_return"):
        assert result[key] is None


@pytest.mark.parametrize(
    ("currency", "ticker", "exchange", "reason"),
    [("GBP", "VOD", "L", "sterling_instrument"), ("GBX", "VOD", "L", "sterling_instrument")],
)
def test_sterling_instruments_have_no_split(stored, usd_meta, currency, ticker, exchange, reason) -> None:
    usd_meta["currency"] = currency

    result = local_fx_return_split(ticker, exchange, START, END)

    assert result["applicable"] is False
    assert result["reason"] == reason
    assert result["currency"] == "GBP"
    assert result["fx_return"] is None and result["gbp_return"] is None


def test_currency_the_closes_are_converted_from_must_match_the_reported_one(stored, monkeypatch) -> None:
    """If the two resolvers disagree the split would not reconcile, so it is refused."""
    monkeypatch.setattr(pu, "instrument_currency", lambda _t, _e: "EUR")

    result = local_fx_return_split("USCO", "N", START, END)

    assert result["reason"] == "currency_mismatch"
    assert result["gbp_return"] is None


def test_fewer_than_two_closes_gives_no_split(stored) -> None:
    stored["closes"] = _closes([END], [110.0])

    result = local_fx_return_split("USCO", "N", START, END)

    assert result["reason"] == "insufficient_price_history"
    assert result["local_return"] is None


def test_scaling_override_cancels_out_of_the_local_return(stored, monkeypatch) -> None:
    monkeypatch.setattr(split_mod, "get_scaling_override", lambda *_args: 0.5)

    assert local_fx_return_split("USCO", "N", START, END)["local_return"] == pytest.approx(0.10)


# ── reconciliation through the real cache-only loader and FX parquet ─────────


@pytest.fixture
def cached_usd(monkeypatch: pytest.MonkeyPatch, tmp_path, usd_meta):
    """A real stored meta parquet and ``timeseries/fx/USD.parquet``; any live fetch explodes."""

    def explode(*_args, **_kwargs):
        raise AssertionError("the FX split is cache-only and must not call Yahoo")

    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "_FX_FRAMES", {})
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", explode)
    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", explode)
    monkeypatch.setattr(cache, "load_meta_timeseries", explode)  # the live price loader
    monkeypatch.setattr(cache.refresh_queue, "enqueue", lambda *_args: False)
    monkeypatch.setattr(cache.refresh_queue, "enqueue_fx", lambda *_args: False)

    def clear_lrus() -> None:
        cache._memoized_range_cached.cache_clear()
        cache._load_meta_parquet_cached.cache_clear()

    def store(closes: pd.DataFrame, rates: dict[date, float]) -> None:
        clear_lrus()
        meta = cache.meta_timeseries_cache_path("USCO", "N")
        cache._ensure_local_dir(meta)
        closes.assign(Open=closes["Close"], High=closes["Close"], Low=closes["Close"], Volume=1000).to_parquet(
            meta, index=False
        )
        path = cache._fx_cache_path("USD")
        cache._ensure_local_dir(path)
        _rates(rates).to_parquet(path, index=False)

    yield store
    clear_lrus()


def _gbp_return_from_close_gbp(start: date, end: date) -> float:
    with cache.cache_only():
        frame = cache.load_meta_timeseries_range("USCO", "N", start_date=start, end_date=end)
    close_gbp = frame.set_index(pd.to_datetime(frame["Date"]))["Close_gbp"].dropna()
    return float(close_gbp.iloc[-1] / close_gbp.iloc[0] - 1)


def test_gbp_return_reconciles_with_close_gbp_from_the_cache_only_loader(cached_usd) -> None:
    days = list(pd.bdate_range(START, END).date)
    closes = [100.0 + 0.7 * i for i in range(len(days))]
    # Rates on Mon/Wed/Fri only: Tue/Thu closes carry the previous stored rate.
    rates = {day: 0.80 - 0.002 * i for i, day in enumerate(days) if day.weekday() in (0, 2, 4)}
    cached_usd(_closes(days, closes), rates)

    result = local_fx_return_split("USCO", "N", START, END)

    assert result["reason"] is None
    assert result["end"] == days[-1].isoformat()
    assert result["gbp_return"] == pytest.approx(_gbp_return_from_close_gbp(START, END), abs=1e-12)


def test_fx_split_route_is_cache_only_and_returns_the_split(cached_usd, monkeypatch) -> None:
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    today = date.today()
    days = [today - timedelta(days=30), today - timedelta(days=1)]
    cached_usd(_closes(days, [200.0, 220.0]), {days[0]: 0.80, days[1]: 0.76})

    resp = TestClient(create_app()).get("/instrument/fx-split?ticker=USCO.N&days=365")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "USCO.N"
    assert body["local_return"] == pytest.approx(0.10)
    assert body["fx_return"] == pytest.approx(-0.05)
    assert body["cross_term"] == pytest.approx(-0.005)
    assert body["gbp_return"] == pytest.approx(0.045)
