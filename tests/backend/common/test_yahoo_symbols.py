"""Yahoo Finance symbols: suffixes, and the dash for US share classes (#11081, #11084)."""

import pytest

from backend.common.yahoo_symbols import yahoo_share_class_symbol, yahoo_symbol_for
from backend.timeseries.fetch_yahoo_timeseries import _build_full_ticker


@pytest.mark.parametrize(
    "symbol,exchange,expected",
    [
        ("BRK.B", "N", "BRK-B"),
        ("BF.B", "US", "BF-B"),
        ("brk.a", "nyse", "BRK-A"),
        ("MOG.A", "NASDAQ", "MOG-A"),
        ("AAPL", "US", "AAPL"),
    ],
)
def test_us_share_class_takes_dash(symbol, exchange, expected):
    assert yahoo_share_class_symbol(symbol, exchange) == expected


@pytest.mark.parametrize(
    "symbol,exchange",
    [
        ("BP.L", "L"),
        ("BT.A", "LSE"),
        ("BP.", "L"),
        ("IWDA.AS", "US"),
        ("^GSPC", "US"),
        ("GBPUSD=X", "FX"),
        ("7203.T", "US"),
        ("RDS.AB", "N"),
    ],
)
def test_other_symbols_unchanged(symbol, exchange):
    assert yahoo_share_class_symbol(symbol, exchange) == symbol


_SYMBOL_FOR_CASES = [
    ("XDEV", "L", "XDEV.L"),
    ("xdev", "l", "XDEV.L"),
    ("XDEV.L", "L", "XDEV.L"),
    ("BP.L", "L", "BP.L"),
    ("BT.A", "L", "BT.A.L"),
    ("PFE", "NASDAQ", "PFE"),
    ("BRK.B", "US", "BRK-B"),
    ("bf.b", "N", "BF-B"),
    ("RDS.AB", "N", "RDS.AB"),
    ("^GSPC", "US", "^GSPC"),
    ("GBPUSD", "FX", "GBPUSD=X"),
    ("GBPUSD=X", "FX", "GBPUSD=X"),
    ("SAP", "XETRA", "SAP.DE"),
]


@pytest.mark.parametrize("ticker,exchange,expected", _SYMBOL_FOR_CASES)
def test_yahoo_symbol_for(ticker, exchange, expected):
    """Exchange suffix added once, US share-class dot swapped for a dash (#11084)."""
    assert yahoo_symbol_for(ticker, exchange) == expected


@pytest.mark.parametrize("ticker,exchange,expected", _SYMBOL_FOR_CASES)
def test_build_full_ticker_is_an_alias(ticker, exchange, expected):
    assert _build_full_ticker(ticker, exchange) == yahoo_symbol_for(ticker, exchange)


def test_yahoo_symbol_for_unknown_exchange():
    with pytest.raises(ValueError):
        yahoo_symbol_for("TEST", "MOON")
