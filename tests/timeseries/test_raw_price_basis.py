"""Yahoo prices are stored on the traded basis, with dividends stored separately (#9340)."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from backend.timeseries import corporate_actions, fetch_yahoo_timeseries, timeseries_api
from backend.timeseries.corporate_actions import (
    DIVIDEND,
    SPLIT,
    load_corporate_actions,
    load_dividends,
    merge_actions,
    record_corporate_actions,
)
from backend.timeseries.fetch_yahoo_timeseries import (
    fetch_yahoo_timeseries_period,
    fetch_yahoo_timeseries_range,
)


class _HistoryMetadata(Mapping):
    """Like yfinance 1.7's ``HistoryMetadata``: a read-only Mapping, *not* a dict."""

    def __init__(self, data: dict):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class FakeYahooTicker:
    """Mimics ``yfinance.Ticker.history`` adjustment semantics without the network.

    Like yfinance, the default is ``auto_adjust=True``: ``Close`` comes back
    dividend-adjusted *as of the call*. With ``auto_adjust=False`` the traded
    ``Close`` is returned plus ``Adj Close``. ``actions=True`` (the default)
    adds ``Dividends``/``Stock Splits`` columns.
    """

    def __init__(self, closes: pd.Series, dividends: dict[pd.Timestamp, float], currency: str = "GBP"):
        self.closes = closes
        self.dividends = dividends
        self.history_metadata = _HistoryMetadata({"currency": currency})
        self.calls: list[dict] = []

    def _adjusted(self) -> pd.Series:
        factor = pd.Series(1.0, index=self.closes.index)
        for ex_date, amount in self.dividends.items():
            before = self.closes.index < ex_date
            if not before.any():
                continue
            prev_close = self.closes[before].iloc[-1]
            factor[before] *= 1.0 - amount / prev_close
        return self.closes * factor

    def history(self, start=None, end=None, interval="1d", auto_adjust=True, actions=True, **_kw):
        self.calls.append({"start": start, "end": end, "auto_adjust": auto_adjust, "actions": actions})
        index = self.closes.index
        mask = (index >= pd.Timestamp(start)) & (index < pd.Timestamp(end))
        raw = self.closes[mask]
        adjusted = self._adjusted()[mask]
        close = adjusted if auto_adjust else raw
        frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1000})
        if not auto_adjust:
            frame.insert(4, "Adj Close", adjusted)
        if actions:
            frame["Dividends"] = [self.dividends.get(day, 0.0) for day in raw.index]
            frame["Stock Splits"] = 0.0
        frame.index = frame.index.tz_localize("Europe/London")
        frame.index.name = "Date"
        return frame


@pytest.fixture
def cache_base(monkeypatch, tmp_path):
    cache = importlib.import_module("backend.timeseries.cache")
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(fetch_yahoo_timeseries, "is_valid_ticker", lambda *_a: True)
    return cache


def _history_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    frame.index.name = "Date"
    return frame


# ── explicit basis at every call site ─────────────────────────


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_range_fetch_requests_traded_prices_and_actions(mock_ticker_cls, cache_base):
    stock = Mock()
    stock.history.return_value = _history_frame()
    mock_ticker_cls.return_value = stock

    fetch_yahoo_timeseries_range("ABC", "L", date(2024, 1, 2), date(2024, 1, 2))

    kwargs = stock.history.call_args.kwargs
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is True


@patch("backend.timeseries.fetch_yahoo_timeseries.yf.Ticker")
def test_period_fetch_requests_traded_prices(mock_ticker_cls):
    stock = Mock()
    stock.history.return_value = _history_frame()
    mock_ticker_cls.return_value = stock

    fetch_yahoo_timeseries_period("ABC", "L", period="5d")

    assert stock.history.call_args.kwargs["auto_adjust"] is False


@patch("backend.timeseries.timeseries_api.yf.Ticker")
def test_download_endpoint_requests_traded_prices(mock_ticker_cls):
    stock = Mock()
    stock.history.return_value = _history_frame()
    mock_ticker_cls.return_value = stock

    timeseries_api._fetch_yahoo("ABC.L", "5d", "1d")

    assert stock.history.call_args.kwargs["auto_adjust"] is False


def test_fetch_stores_traded_close_not_adjusted_close(cache_base):
    days = pd.bdate_range("2024-03-01", periods=5)
    closes = pd.Series([100.0, 101.0, 102.0, 100.0, 101.0], index=days)
    fake = FakeYahooTicker(closes, {days[3]: 2.0})

    with patch.object(fetch_yahoo_timeseries.yf, "Ticker", return_value=fake):
        df = fetch_yahoo_timeseries_range("ABC", "L", days[0].date(), days[-1].date())

    assert df["Close"].tolist() == closes.tolist()
    # Sanity check on the fake: yfinance's default would have re-based the history.
    assert fake.history(start=days[0], end=days[-1] + timedelta(days=1))["Close"].iloc[0] < 100.0


# ── dividend / split storage ──────────────────────────────────


def _one_dividend() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": [pd.Timestamp("2024-01-10")],
            "Action": [DIVIDEND],
            "Value": [1.0],
            "Currency": ["GBP"],
            "Source": ["Yahoo"],
        }
    )


def test_fetch_stores_dividends_and_loader_reads_them(cache_base):
    days = pd.bdate_range("2024-03-01", periods=5)
    closes = pd.Series([100.0, 101.0, 102.0, 100.0, 101.0], index=days)
    fake = FakeYahooTicker(closes, {days[3]: 2.0}, currency="GBp")

    with patch.object(fetch_yahoo_timeseries.yf, "Ticker", return_value=fake):
        fetch_yahoo_timeseries_range("ABC", "L", days[0].date(), days[-1].date())

    dividends = load_dividends("ABC", "L")
    assert dividends.to_dict() == {pd.Timestamp(days[3].date()): 2.0}
    stored = load_corporate_actions("ABC", "L")
    assert stored[["Action", "Currency", "Source"]].values.tolist() == [[DIVIDEND, "GBp", "Yahoo"]]
    expected = importlib.import_module("pathlib").Path(cache_base._CACHE_BASE, "corporate_actions", "ABC_L.parquet")
    assert expected.is_file()


def test_store_actions_false_does_not_write(cache_base):
    days = pd.bdate_range("2024-03-01", periods=5)
    fake = FakeYahooTicker(pd.Series(100.0, index=days), {days[2]: 1.0})

    with patch.object(fetch_yahoo_timeseries.yf, "Ticker", return_value=fake):
        fetch_yahoo_timeseries_range("ABC", "L", days[0].date(), days[-1].date(), store_actions=False)

    assert load_dividends("ABC", "L").empty


def test_actions_merge_incrementally_and_skip_identical_writes(cache_base):
    first = _one_dividend()
    second = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2024-01-10"), pd.Timestamp("2024-04-10"), pd.Timestamp("2024-05-01")],
            "Action": [DIVIDEND, DIVIDEND, SPLIT],
            "Value": [1.0, 1.2, 2.0],
            "Currency": ["GBP", "GBP", "GBP"],
            "Source": ["Yahoo", "Yahoo", "Yahoo"],
        }
    )

    assert record_corporate_actions("ABC", "L", first) is True
    assert record_corporate_actions("ABC", "L", first) is False
    assert record_corporate_actions("ABC", "L", second) is True

    stored = load_corporate_actions("ABC", "L")
    assert stored["Action"].tolist() == [DIVIDEND, DIVIDEND, SPLIT]
    assert load_dividends("ABC", "L").tolist() == [1.0, 1.2]


def test_merge_actions_reports_value_corrections():
    base = _one_dividend()
    corrected = base.assign(Value=[1.05])

    merged, changed = merge_actions(base, corrected)

    assert changed is True
    assert merged["Value"].tolist() == [1.05]
    assert merge_actions(base, base.copy())[1] is False


def test_unreadable_actions_file_is_logged_and_treated_as_empty(cache_base, caplog):
    path = corporate_actions.corporate_actions_path("ABC", "L")
    importlib.import_module("pathlib").Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("not parquet")

    with caplog.at_level(logging.WARNING):
        assert load_dividends("ABC", "L").empty
    assert "Could not read corporate actions" in caplog.text


# ── rolling-cache overlap re-fetch across an ex-date ──────────


def test_overlap_refetch_after_ex_date_leaves_earlier_closes_unchanged(cache_base):
    """The issue's failure mode: an overlap re-fetch after a dividend must not re-base history."""
    cache = cache_base
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 60)
    days = pd.bdate_range(end=pd.Timestamp(window_end), periods=40)
    closes = pd.Series([100.0 + (i % 7) for i in range(len(days))], index=days)
    ex_date = days[-3]
    fake = FakeYahooTicker(closes, {ex_date: 3.0})

    # Cache as stored before the ex-date: traded closes up to five days before the end.
    seeded = days[:-5]
    path = cache._cache_path("meta", "ABC_L.parquet")
    cache._save_parquet(
        pd.DataFrame(
            {
                "Date": seeded,
                "Open": closes[seeded].to_numpy(),
                "High": closes[seeded].to_numpy(),
                "Low": closes[seeded].to_numpy(),
                "Close": closes[seeded].to_numpy(),
                "Volume": 1000.0,
                "Ticker": "ABC.L",
                "Source": "Yahoo",
            }
        ),
        path,
    )

    with patch.object(fetch_yahoo_timeseries.yf, "Ticker", return_value=fake):
        cache._rolling_cache(
            fetch_yahoo_timeseries_range,
            path,
            {"ticker": "ABC", "exchange": "L"},
            40,
            ticker="ABC",
            exchange="L",
        )

    # The re-fetch did cover cached history before the ex-date...
    assert pd.Timestamp(fake.calls[-1]["start"]) < ex_date
    stored = cache._load_parquet(path).set_index("Date")["Close"]
    # ...yet every stored close equals the traded price, before and after it.
    assert stored.index.max() == days[-1]
    assert stored.to_dict() == closes.to_dict()
    assert load_dividends("ABC", "L").to_dict() == {pd.Timestamp(ex_date.date()): 3.0}


def test_history_currency_reads_yfinance_mapping_metadata():
    """yfinance 1.7 returns HistoryMetadata (a Mapping, not a dict); the currency must still be read."""
    stock = Mock(history_metadata=_HistoryMetadata({"currency": "GBp"}))
    assert fetch_yahoo_timeseries._history_currency(stock) == "GBp"
    assert fetch_yahoo_timeseries._history_currency(Mock(history_metadata={"currency": "USD"})) == "USD"
    assert fetch_yahoo_timeseries._history_currency(Mock(history_metadata=None)) is None
    assert fetch_yahoo_timeseries._history_currency(Mock(history_metadata=_HistoryMetadata({"currency": ""}))) is None
