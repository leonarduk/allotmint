"""Tests for regional sector performance and sector drill-down (#9381)."""

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import market_sectors
from backend.routes import market


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(market.router)
    return TestClient(app)


def _closes(data: dict, start: str = "2025-12-29", dividends: dict | None = None) -> pd.DataFrame:
    """Build a yfinance-shaped download frame with ``Close`` (and ``Dividends``) columns."""

    length = len(next(iter(data.values())))
    index = pd.bdate_range(start, periods=length)
    columns = pd.MultiIndex.from_product([["Close"], list(data)], names=["Price", "Ticker"])
    rows = list(zip(*data.values(), strict=True))
    frame = pd.DataFrame(rows, columns=columns, index=index)
    if dividends:
        paid = pd.DataFrame(0.0, index=index, columns=pd.MultiIndex.from_product([["Dividends"], list(data)]))
        for (symbol, row), amount in dividends.items():
            paid.iloc[row, paid.columns.get_loc(("Dividends", symbol))] = amount
        frame = pd.concat([frame, paid], axis=1)
    return frame


SMALL_UNIVERSE = {
    "us": {
        "Energy": {"proxy": ("XLE", "Energy SPDR"), "constituents": [("XOM", "Exxon"), ("CVX", "Chevron")]},
        "Utilities": {"proxy": ("XLU", "Utilities SPDR"), "constituents": [("NEE", "NextEra")]},
    },
    "uk": {
        "Energy": {"proxy": None, "constituents": [("SHEL.L", "Shell"), ("BP.L", "BP")]},
    },
    "global": {},
}


@pytest.fixture
def small_universe(monkeypatch):
    monkeypatch.setattr(market_sectors, "SECTOR_UNIVERSE", SMALL_UNIVERSE)


def test_every_region_covers_the_same_sectors():
    names = {region: set(sectors) for region, sectors in market_sectors.SECTOR_UNIVERSE.items()}
    assert set(names) == set(market_sectors.REGIONS)
    assert names["global"] == names["us"] == names["uk"]
    for sectors in market_sectors.SECTOR_UNIVERSE.values():
        for definition in sectors.values():
            assert definition["constituents"]


def test_fetch_region_sectors_uses_etf_proxy(monkeypatch, small_universe):
    frame = _closes({"XLE": [100.0, 102.0], "XLU": [50.0, 49.0]})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    rows = market_sectors.fetch_region_sectors("us")

    assert rows == [
        {"sector": "Energy", "change": pytest.approx(2.0), "source": "etf"},
        {"sector": "Utilities", "change": pytest.approx(-2.0), "source": "etf"},
    ]


def test_fetch_region_sectors_averages_uk_basket(monkeypatch, small_universe):
    frame = _closes({"SHEL.L": [10.0, 11.0], "BP.L": [5.0, 5.0]})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    rows = market_sectors.fetch_region_sectors("uk")

    assert rows == [{"sector": "Energy", "change": pytest.approx(5.0), "source": "basket"}]


@pytest.mark.parametrize(
    ("period", "download_window", "expected"),
    [
        # 2026-01-01 .. 2026-12-31 business days; latest close is 200.
        ("1W", "1mo", (200 - 190) / 190 * 100),
        ("1M", "3mo", (200 - 170) / 170 * 100),
        ("3M", "6mo", (200 - 130) / 130 * 100),
        ("1Y", "2y", 100.0),
    ],
)
def test_fetch_region_sectors_over_period(monkeypatch, small_universe, period, download_window, expected):
    index = pd.bdate_range("2025-12-31", "2026-12-31")
    last = index[-1]
    days = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365}[period]
    cutoff = last - pd.Timedelta(days=days)
    # Flat at the base price up to the cutoff, then the latest close jumps.
    base = {"1W": 190.0, "1M": 170.0, "3M": 130.0, "1Y": 100.0}[period]
    xle = [base if day <= cutoff else 150.0 for day in index]
    xle[-1] = 200.0
    columns = pd.MultiIndex.from_product([["Close"], ["XLE", "XLU"]])
    frame = pd.DataFrame(list(zip(xle, [50.0] * len(index), strict=True)), columns=columns, index=index)
    windows = []

    def fake_download(symbols, period, **_):
        windows.append(period)
        return frame

    monkeypatch.setattr(market_sectors.yf, "download", fake_download)

    rows = market_sectors.fetch_region_sectors("us", period)

    assert windows == [download_window]
    assert rows[0] == {"sector": "Energy", "change": pytest.approx(expected), "source": "etf"}
    assert rows[1]["change"] == pytest.approx(0.0)


def test_fetch_region_sectors_basket_over_period(monkeypatch, small_universe):
    # Business days from 2025-12-29; the 1W cutoff for the last row is
    # seven calendar days back, i.e. five rows earlier.
    frame = _closes({"SHEL.L": [10.0] * 3 + [12.0] * 5, "BP.L": [5.0] * 3 + [4.0] * 5})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    rows = market_sectors.fetch_region_sectors("uk", "1W")

    # Mean of +20% and -20%.
    assert rows == [{"sector": "Energy", "change": pytest.approx(0.0), "source": "basket"}]


def test_period_change_without_enough_history_is_none():
    series = pd.Series([1.0, 2.0], index=pd.bdate_range("2026-01-01", periods=2))
    assert market_sectors.period_change(series, "1M") is None
    assert market_sectors.period_change(pd.Series(dtype=float), "1W") is None


@pytest.mark.parametrize(("raw", "expected"), [("1d", "1D"), (" 1y ", "1Y"), ("3M", "3M"), ("5Y", None), (None, None)])
def test_normalise_period(raw, expected):
    assert market_sectors.normalise_period(raw) == expected


def test_fetch_region_sectors_reinvests_dividends(monkeypatch, small_universe):
    # XLE flat at 100 but goes ex a 4 dividend inside the week: total return is +4%,
    # where the traded price alone would show 0%.
    frame = _closes(
        {"XLE": [100.0] * 8, "XLU": [50.0] * 8},
        dividends={("XLE", 4): 4.0},
    )
    calls = []

    def fake_download(*_args, **kwargs):
        calls.append(kwargs)
        return frame

    monkeypatch.setattr(market_sectors.yf, "download", fake_download)

    rows = market_sectors.fetch_region_sectors("us", "1W")

    assert rows[0] == {"sector": "Energy", "change": pytest.approx(4.0), "source": "etf"}
    assert rows[1]["change"] == pytest.approx(0.0)
    # Traded closes plus Yahoo's dividend column, never the re-based adjusted Close.
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["actions"] is True


def test_basket_change_reinvests_constituent_dividends(monkeypatch, small_universe):
    frame = _closes(
        {"SHEL.L": [10.0] * 8, "BP.L": [5.0] * 8},
        dividends={("SHEL.L", 4): 0.5},
    )
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    rows = market_sectors.fetch_region_sectors("uk", "1W")

    # Mean of +5% (Shell's dividend) and 0% (BP).
    assert rows == [{"sector": "Energy", "change": pytest.approx(2.5), "source": "basket"}]


def test_sector_detail_reports_traded_price_and_total_return(monkeypatch, small_universe):
    frame = _closes(
        {"XLE": [100.0] * 8, "XOM": [50.0] * 8, "CVX": [None] * 8},
        dividends={("XLE", 3): 2.0, ("XOM", 7): 1.0},
    )
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    detail = market_sectors.fetch_sector_detail("us", "Energy")

    assert detail["returns"]["1W"] == pytest.approx(2.0)
    xom = detail["constituents"][0]
    # Price is the traded close; the day change includes the dividend going ex.
    assert xom["price"] == 50.0
    assert xom["change"] == pytest.approx(2.0)


def test_indexes_level_is_traded_close_even_with_dividends(monkeypatch):
    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"FTSE 100": "^FTSE"})
    frame = _closes({"^FTSE": [100.0] * 8}, dividends={("^FTSE", 5): 1.0})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    resp = _client().get("/market/indexes", params={"period": "1W"})

    assert resp.json()["indexes"]["FTSE 100"] == {"value": 100.0, "change": pytest.approx(1.0)}


def test_fetch_region_sectors_skips_sector_without_data(monkeypatch, small_universe):
    frame = _closes({"XLE": [100.0, 101.0], "XLU": [None, None]})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    rows = market_sectors.fetch_region_sectors("us")

    assert [r["sector"] for r in rows] == ["Energy"]


def test_fetch_sector_detail_etf_returns_and_constituents(monkeypatch, small_universe):
    # 2025-12-29 .. : the 2025-12-31 close (index 2) is the YTD base.
    xle = [90.0, 95.0, 100.0] + [100.0 + i for i in range(1, 30)]
    frame = _closes(
        {
            "XLE": xle,
            "XOM": [50.0] * (len(xle) - 1) + [55.0],
            "CVX": [None] * len(xle),
        }
    )
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    detail = market_sectors.fetch_sector_detail("us", "Energy")

    assert detail["basis"] == "etf"
    assert detail["proxy"] == {"ticker": "XLE", "name": "Energy SPDR"}
    assert detail["returns"]["YTD"] == pytest.approx(29.0)
    assert detail["returns"]["1D"] == pytest.approx((129 - 128) / 128 * 100)
    # 1W base is the last close on or before seven calendar days earlier.
    assert detail["returns"]["1W"] == pytest.approx((129 - 124) / 124 * 100)
    assert detail["history"][-1]["value"] == pytest.approx(129.0)
    assert detail["constituents"] == [
        {"ticker": "XOM", "name": "Exxon", "price": 55.0, "change": pytest.approx(10.0)},
        {"ticker": "CVX", "name": "Chevron", "price": None, "change": None},
    ]


def test_fetch_sector_detail_uk_builds_equal_weight_index(monkeypatch, small_universe):
    frame = _closes({"SHEL.L": [10.0, 12.0], "BP.L": [4.0, 4.0]})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    detail = market_sectors.fetch_sector_detail("uk", "Energy")

    assert detail["basis"] == "basket"
    assert detail["proxy"] is None
    assert [p["value"] for p in detail["history"]] == [100.0, pytest.approx(110.0)]
    assert detail["returns"]["1D"] == pytest.approx(10.0)


def test_basket_index_ignores_constituent_without_data(monkeypatch, small_universe):
    frame = _closes({"SHEL.L": [10.0, 11.0], "BP.L": [None, None]})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    detail = market_sectors.fetch_sector_detail("uk", "Energy")

    assert [p["value"] for p in detail["history"]] == [100.0, pytest.approx(110.0)]
    assert detail["returns"]["1D"] == pytest.approx(10.0)


def test_sectors_endpoint_uses_configured_default_region(monkeypatch):
    monkeypatch.setattr(market.cfg, "default_sector_region", "UK", raising=False)
    calls = []

    def fake_fetch(region, period):
        calls.append((region, period))
        return [{"sector": "Energy", "change": 1.0, "source": "basket"}]

    monkeypatch.setattr(market_sectors, "fetch_region_sectors", fake_fetch)

    resp = _client().get("/market/sectors")

    assert resp.status_code == 200
    assert resp.json() == {
        "region": "uk",
        "period": "1D",
        "sectors": [{"sector": "Energy", "change": 1.0, "source": "basket"}],
    }
    assert calls == [("uk", "1D")]


def test_sectors_endpoint_passes_period(monkeypatch):
    calls = []

    def fake_fetch(region, period):
        calls.append((region, period))
        return []

    monkeypatch.setattr(market_sectors, "fetch_region_sectors", fake_fetch)

    resp = _client().get("/market/sectors", params={"region": "us", "period": "3m"})

    assert resp.status_code == 200
    assert resp.json()["period"] == "3M"
    assert calls == [("us", "3M")]


def test_sectors_endpoint_rejects_unknown_period():
    resp = _client().get("/market/sectors", params={"period": "5Y"})
    assert resp.status_code == 400


def test_sectors_endpoint_rejects_unknown_region():
    resp = _client().get("/market/sectors", params={"region": "mars"})
    assert resp.status_code == 400


def test_sectors_endpoint_reports_upstream_failure(monkeypatch):
    def boom(_region, _period):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(market_sectors, "fetch_region_sectors", boom)

    resp = _client().get("/market/sectors", params={"region": "global"})

    assert resp.status_code == 502


def test_sector_detail_endpoint_matches_name_case_insensitively(monkeypatch):
    captured = {}

    def fake_detail(region, sector):
        captured["args"] = (region, sector)
        return {"region": region, "sector": sector}

    monkeypatch.setattr(market_sectors, "fetch_sector_detail", fake_detail)

    resp = _client().get("/market/sectors/US/health%20care")

    assert resp.status_code == 200
    assert captured["args"] == ("us", "Health Care")


@pytest.mark.parametrize("path", ["/market/sectors/mars/Energy", "/market/sectors/us/Crypto"])
def test_sector_detail_endpoint_404s_unknown(path):
    assert _client().get(path).status_code == 404


def test_indexes_endpoint_uses_live_quote_for_one_day(monkeypatch):
    monkeypatch.setattr(market, "_fetch_indexes", lambda: {"FTSE 100": {"value": 1.0, "change": 0.5}})

    resp = _client().get("/market/indexes")

    assert resp.status_code == 200
    assert resp.json() == {"period": "1D", "indexes": {"FTSE 100": {"value": 1.0, "change": 0.5}}}


def test_indexes_endpoint_computes_period_change_from_closes(monkeypatch):
    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"FTSE 100": "^FTSE", "FTSE 250": "^FTMC"})
    frame = _closes({"^FTSE": [100.0] * 3 + [110.0] * 5, "^FTMC": [None] * 8})
    windows = []

    def fake_download(symbols, period, **_):
        windows.append((list(symbols), period))
        return frame

    monkeypatch.setattr(market_sectors.yf, "download", fake_download)

    resp = _client().get("/market/indexes", params={"period": "1W"})

    assert resp.status_code == 200
    assert resp.json() == {
        "period": "1W",
        "indexes": {"FTSE 100": {"value": pytest.approx(110.0), "change": pytest.approx(10.0)}},
    }
    assert windows == [(["^FTSE", "^FTMC"], "1mo")]


def test_indexes_endpoint_rejects_unknown_period():
    assert _client().get("/market/indexes", params={"period": "ytd"}).status_code == 400


def test_indexes_endpoint_reports_upstream_failure(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(market_sectors.yf, "download", boom)

    assert _client().get("/market/indexes", params={"period": "1Y"}).status_code == 502


@patch("backend.routes.market._fetch_indexes", return_value={})
@patch("backend.common.market_sectors.fetch_region_sectors")
@patch("backend.routes.market._fetch_headlines", return_value=[])
def test_overview_can_skip_sectors(mock_headlines, mock_sectors, mock_indexes):
    resp = _client().get("/market/overview", params={"sectors": "false"})

    assert resp.status_code == 200
    assert resp.json()["sectors"] == []
    mock_sectors.assert_not_called()
