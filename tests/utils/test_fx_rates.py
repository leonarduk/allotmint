import datetime as dt

import pandas as pd
import pytest
import yfinance as yf

from backend.utils import fx_rates
from backend.utils.fx_rates import (
    FX_RATE_SOURCE_FALLBACK,
    FX_SOURCE_ATTR,
    fallback_fx_rate,
    fallback_fx_rate_range,
    fetch_fx_rate_range,
)


def _fake_df(start, end):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"Date": dates, "Close": [1.0 + i * 0.1 for i in range(len(dates))]})


@pytest.mark.parametrize("base,quote", [("USD", "GBP"), ("CHF", "GBP"), ("JPY", "GBP"), ("CAD", "GBP")])
def test_fetch_fx_rate_range_success(monkeypatch, base, quote):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 3)

    class FakeTicker:
        def history(self, start, end, interval):
            return _fake_df(start, end - dt.timedelta(days=1))

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range(base, quote, start, end)
    assert list(df["Date"]) == [dt.date(2024, 1, 1), dt.date(2024, 1, 2), dt.date(2024, 1, 3)]
    assert list(df["Rate"]) == [1.0, 1.1, 1.2]


def test_fetch_fx_rate_range_empty(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)

    class FakeTicker:
        def history(self, start, end, interval):
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("USD", "GBP", start, end)
    assert list(df["Rate"]) == [0.8, 0.8]
    assert df.attrs[FX_SOURCE_ATTR] == FX_RATE_SOURCE_FALLBACK


def test_fetch_fx_rate_range_exception(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 1)

    class FakeTicker:
        def history(self, start, end, interval):
            raise RuntimeError("boom")

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("EUR", "GBP", start, end)
    assert list(df["Rate"]) == [0.9]


def test_fetch_fx_rate_range_unsupported(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 1)

    class FakeTicker:
        def history(self, start, end, interval):
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    df = fetch_fx_rate_range("AUD", "GBP", start, end)
    # No constant for AUD: no rate at all, never a made-up 1.0 (#9664).
    assert df.empty


def test_fetch_fx_rate_same_currency():
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 3)
    fetch_fx_rate_range.cache_clear()
    df = fetch_fx_rate_range("USD", "USD", start, end)
    assert list(df["Rate"]) == [1.0, 1.0, 1.0]


@pytest.mark.parametrize("base", ["JPY", "CHF", "CAD", "AUD", "SGD"])
def test_fallback_fx_rate_unknown_pair_is_none(base):
    # These currencies have no approximate constant; 1.0 would value e.g.
    # 1 JPY at 1 GBP, a ~190x overstatement (#9664).
    assert fallback_fx_rate(base, "GBP") is None
    assert fallback_fx_rate_range(base, "GBP", dt.date(2024, 1, 1), dt.date(2024, 1, 3)).empty


def test_fallback_fx_rate_known_and_inverse_pairs():
    assert fallback_fx_rate("usd", "gbp") == 0.8
    assert fallback_fx_rate("GBP", "EUR") == pytest.approx(1 / 0.9)


def test_failed_live_fetch_is_not_memoised(monkeypatch):
    """A transient failure must not pin the fallback for the process lifetime (#9664)."""
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)
    responses = [pd.DataFrame(), _fake_df(start, end)]

    class FakeTicker:
        def history(self, start, end, interval):
            return responses.pop(0)

    monkeypatch.setattr(yf, "Ticker", lambda pair: FakeTicker())
    fetch_fx_rate_range.cache_clear()

    first = fetch_fx_rate_range("USD", "GBP", start, end)
    assert first.attrs[FX_SOURCE_ATTR] == FX_RATE_SOURCE_FALLBACK

    second = fetch_fx_rate_range("USD", "GBP", start, end)
    assert list(second["Rate"]) == [1.0, 1.1]
    assert FX_SOURCE_ATTR not in second.attrs


def test_successful_live_fetch_is_memoised(monkeypatch):
    start = dt.date(2024, 1, 1)
    end = dt.date(2024, 1, 2)
    calls = []

    def fake_live(base, quote, start_date, end_date):
        calls.append(base)
        return pd.DataFrame({"Date": [start_date], "Rate": [0.79]})

    monkeypatch.setattr(fx_rates, "fetch_fx_rate_range_live", fake_live)
    fetch_fx_rate_range.cache_clear()

    first = fetch_fx_rate_range("USD", "GBP", start, end)
    first["Rate"] = 0.0  # callers mutating their copy must not corrupt the memo
    second = fetch_fx_rate_range("USD", "GBP", start, end)

    assert calls == ["USD"]
    assert list(second["Rate"]) == [0.79]
