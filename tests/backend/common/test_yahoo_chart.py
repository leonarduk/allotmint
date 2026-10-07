import pandas as pd
import pytest

from backend.common import yahoo_chart
from tests.yahoo_chart_fakes import FakeChartTicker

# 2026-10-05 regular session for an exchange, as epoch seconds.
PRE_START, REG_START, REG_END, POST_END = 1_759_640_400, 1_759_671_000, 1_759_694_400, 1_759_708_800
PERIODS = {
    "pre": {"start": PRE_START, "end": REG_START},
    "regular": {"start": REG_START, "end": REG_END},
    "post": {"start": REG_END, "end": POST_END},
}


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (PRE_START - 1, "CLOSED"),
        (PRE_START, "PRE"),
        (REG_START, "REGULAR"),
        (REG_END - 1, "REGULAR"),
        (REG_END, "POST"),
        (POST_END, "CLOSED"),
    ],
)
def test_market_state_from_epoch_periods(now, expected):
    assert yahoo_chart.market_state({"currentTradingPeriod": PERIODS}, now=now) == expected


def test_market_state_from_formatted_timestamp_periods():
    """yfinance's ``format_history_metadata`` turns the epochs into Timestamps."""

    tz = "America/New_York"
    formatted = {
        key: {edge: pd.Timestamp(value, unit="s", tz="UTC").tz_convert(tz) for edge, value in window.items()}
        for key, window in PERIODS.items()
    }
    assert yahoo_chart.market_state({"currentTradingPeriod": formatted}, now=REG_START + 60) == "REGULAR"


def test_market_state_without_periods_is_none():
    assert yahoo_chart.market_state({}) is None


def test_chart_quote_maps_metadata_to_info_keys():
    metadata = {
        "regularMarketPrice": 110.0,
        "chartPreviousClose": 100.0,
        "regularMarketDayHigh": 112.0,
        "regularMarketDayLow": 99.5,
        "regularMarketVolume": 12345,
        "regularMarketTime": pd.Timestamp(REG_START + 600, unit="s", tz="UTC").tz_convert("Europe/London"),
        "exchangeTimezoneName": "Europe/London",
        "longName": "Long Name plc",
        "shortName": "LONG NAME",
        "currency": "GBp",
        "instrumentType": "EQUITY",
        "currentTradingPeriod": PERIODS,
    }
    history = pd.DataFrame({"Open": [101.0], "Close": [109.0]})
    ticker = FakeChartTicker(metadata, history)

    info = yahoo_chart.chart_quote(ticker)

    assert ticker.history_calls == [{"period": "1d", "interval": "1d", "auto_adjust": False}]
    assert info["regularMarketPrice"] == 110.0
    assert info["regularMarketPreviousClose"] == 100.0
    assert info["regularMarketChangePercent"] == pytest.approx(10.0)
    assert info["regularMarketOpen"] == 101.0
    assert info["regularMarketDayHigh"] == 112.0
    assert info["regularMarketDayLow"] == 99.5
    assert info["regularMarketVolume"] == 12345
    # Epoch seconds, as ``.info`` returned and the frontend expects.
    assert info["regularMarketTime"] == REG_START + 600
    assert info["exchangeTimezoneName"] == "Europe/London"
    assert info["longName"] == "Long Name plc"
    assert info["shortName"] == "LONG NAME"
    assert info["currency"] == "GBp"
    assert info["quoteType"] == "EQUITY"
    assert info["marketState"] in {"PRE", "REGULAR", "POST", "CLOSED"}


def test_chart_quote_falls_back_to_last_close_and_previous_close():
    metadata = {"previousClose": 50.0}
    history = pd.DataFrame({"Open": [48.0, None], "Close": [49.0, 55.0]})

    info = yahoo_chart.chart_quote(FakeChartTicker(metadata, history))

    assert info["regularMarketPrice"] == 55.0
    assert info["regularMarketPreviousClose"] == 50.0
    assert info["regularMarketChangePercent"] == pytest.approx(10.0)
    # Last non-null open, skipping the null in the final row.
    assert info["regularMarketOpen"] == 48.0


def test_chart_quote_with_no_data_returns_nones():
    info = yahoo_chart.chart_quote(FakeChartTicker())

    assert info["regularMarketPrice"] is None
    assert info["regularMarketChangePercent"] is None
    assert info["regularMarketOpen"] is None
    assert info["regularMarketTime"] is None
    assert info["marketState"] is None


def test_chart_quote_zero_previous_close_has_no_change_percent():
    info = yahoo_chart.chart_quote(FakeChartTicker({"regularMarketPrice": 5.0, "chartPreviousClose": 0}))
    assert info["regularMarketChangePercent"] is None


def test_chart_quote_propagates_fetch_errors():
    with pytest.raises(RuntimeError, match="rate limited"):
        yahoo_chart.chart_quote(FakeChartTicker(error=RuntimeError("rate limited")))


def test_chart_quote_treats_zero_and_nan_prices_as_missing():
    """Yahoo zero-fills fields it has no data for; those must not reach callers as 0.00 (#7819)."""

    metadata = {
        "regularMarketPrice": 23999.0,
        "chartPreviousClose": 24090.0,
        "regularMarketDayHigh": 0,
        "regularMarketDayLow": float("nan"),
    }
    history = pd.DataFrame({"Open": [0.0], "Close": [23999.0]})

    info = yahoo_chart.chart_quote(FakeChartTicker(metadata, history))

    assert info["regularMarketPrice"] == 23999.0
    assert info["regularMarketChangePercent"] == pytest.approx((23999.0 - 24090.0) / 24090.0 * 100)
    assert info["regularMarketOpen"] is None
    assert info["regularMarketDayHigh"] is None
    assert info["regularMarketDayLow"] is None


def test_chart_quote_zero_price_falls_back_to_close_and_zero_chart_close_to_previous_close():
    metadata = {"regularMarketPrice": 0, "chartPreviousClose": 0, "previousClose": 50.0}
    history = pd.DataFrame({"Open": [48.0], "Close": [50.0]})

    info = yahoo_chart.chart_quote(FakeChartTicker(metadata, history))

    assert info["regularMarketPrice"] == 50.0
    assert info["regularMarketPreviousClose"] == 50.0
    # A genuinely flat session is still a real 0% change, not "missing".
    assert info["regularMarketChangePercent"] == 0.0
