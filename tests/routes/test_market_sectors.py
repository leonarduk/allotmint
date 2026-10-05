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


def _closes(data: dict, start: str = "2025-12-29") -> pd.DataFrame:
    """Build a yfinance-shaped download frame with ``Close`` columns."""

    length = len(next(iter(data.values())))
    columns = pd.MultiIndex.from_product([["Close"], list(data)], names=["Price", "Ticker"])
    rows = list(zip(*data.values(), strict=True))
    return pd.DataFrame(rows, columns=columns, index=pd.bdate_range(start, periods=length))


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
    assert detail["history"][-1]["value"] == 129.0
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


def test_sectors_endpoint_uses_configured_default_region(monkeypatch):
    monkeypatch.setattr(market.cfg, "default_sector_region", "UK", raising=False)
    calls = []

    def fake_fetch(region):
        calls.append(region)
        return [{"sector": "Energy", "change": 1.0, "source": "basket"}]

    monkeypatch.setattr(market_sectors, "fetch_region_sectors", fake_fetch)

    resp = _client().get("/market/sectors")

    assert resp.status_code == 200
    assert resp.json() == {"region": "uk", "sectors": [{"sector": "Energy", "change": 1.0, "source": "basket"}]}
    assert calls == ["uk"]


def test_sectors_endpoint_rejects_unknown_region():
    resp = _client().get("/market/sectors", params={"region": "mars"})
    assert resp.status_code == 400


def test_sectors_endpoint_reports_upstream_failure(monkeypatch):
    def boom(_region):
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


@patch("backend.routes.market._fetch_indexes", return_value={})
@patch("backend.routes.market._fetch_sectors")
@patch("backend.routes.market._fetch_headlines", return_value=[])
def test_overview_can_skip_sectors(mock_headlines, mock_sectors, mock_indexes):
    resp = _client().get("/market/overview", params={"sectors": "false"})

    assert resp.status_code == 200
    assert resp.json()["sectors"] == []
    mock_sectors.assert_not_called()
