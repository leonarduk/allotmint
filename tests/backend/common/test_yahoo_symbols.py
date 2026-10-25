"""US share classes take Yahoo's dash; nothing else changes (#11081)."""

import pytest

from backend.common.yahoo_symbols import yahoo_share_class_symbol


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
