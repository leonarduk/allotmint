"""Tests for the market overview helpers and HTTP endpoint."""

import threading
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import market
from tests.yahoo_chart_fakes import FakeChartTicker


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(market.router)
    return TestClient(app)


def test_fetch_indexes_with_mocked_yfinance(monkeypatch):
    symbols = list(market.INDEX_SYMBOLS.items())
    last_symbol = symbols[-1][1]

    def fake_tickers(requested: str) -> SimpleNamespace:
        assert requested == " ".join(market.INDEX_SYMBOLS.values())
        tickers = {}
        for idx, (name, sym) in enumerate(symbols, start=1):
            # Odd indexes report a previous close (so a change %); even ones
            # don't, which must fall back to a 0.0 change.
            metadata = {"regularMarketPrice": idx * 100}
            if idx % 2:
                metadata["chartPreviousClose"] = 80.0 * idx
            if sym == last_symbol:
                metadata["regularMarketPrice"] = None
            tickers[sym] = FakeChartTicker(metadata)
        return SimpleNamespace(tickers=tickers)

    monkeypatch.setattr(market.yf, "Tickers", fake_tickers)

    result = market._fetch_indexes()

    expected = {}
    for idx, (name, sym) in enumerate(symbols, start=1):
        if sym == last_symbol:
            continue
        expected[name] = {
            "value": float(idx * 100),
            # (100 * idx - 80 * idx) / (80 * idx) * 100
            "change": 25.0 if idx % 2 else 0.0,
        }

    assert result == expected


def test_fetch_indexes_reports_when_each_level_was_struck(monkeypatch):
    """Each index carries its quote time so the page can show an "as of" (#7788)."""

    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"Timed": "^T", "Untimed": "^U"})
    tickers = {
        "^T": FakeChartTicker({"regularMarketPrice": 100.0, "regularMarketTime": 1_758_200_000}),
        "^U": FakeChartTicker({"regularMarketPrice": 50.0}),
    }
    monkeypatch.setattr(market.yf, "Tickers", lambda _requested: SimpleNamespace(tickers=tickers))

    result = market._fetch_indexes()

    assert result["Timed"]["as_of"] == "2025-09-18T12:53:20+00:00"
    assert "as_of" not in result["Untimed"]


def test_fetch_headlines_with_mocked_news(monkeypatch):
    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"One": "ONE", "Two": "TWO"})
    calls = []
    responses = {
        "ONE": [
            {"url": "https://example.test/1", "headline": "First"},
            {"url": "https://example.test/1", "headline": "Duplicate url"},
            {"headline": "Second"},
        ],
        "TWO": [
            {"headline": "Second"},
            {"url": "https://example.test/3", "headline": "Third"},
            {},
        ],
    }

    def fake_get_cached_news(symbol, **_kwargs):
        calls.append(symbol)
        return responses[symbol]

    monkeypatch.setattr(market, "get_cached_news", fake_get_cached_news)

    headlines = market._fetch_headlines()

    assert calls == ["ONE", "TWO"]
    assert headlines == [
        {"url": "https://example.test/1", "headline": "First"},
        {"headline": "Second"},
        {"url": "https://example.test/3", "headline": "Third"},
    ]


def test_fetch_headlines_propagates_stale_flag_from_get_cached_news(monkeypatch):
    """End-to-end through market_overview: a stale cache flag from
    ``get_cached_news`` must survive ``_fetch_headlines`` and reach the
    ``/market/overview`` response, not just the unit-level helper.
    """

    from backend.routes import news as news_module
    from backend.utils import page_cache

    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"One": "ONE"})
    monkeypatch.setattr(market, "_fetch_indexes", lambda: {})
    monkeypatch.setattr(market.market_sectors, "fetch_region_sectors", lambda _region: [])

    cache = {"news_ONE": [{"headline": "Old headline", "url": "https://example.test/old"}]}

    monkeypatch.setattr(page_cache, "load_cache", lambda page: cache.get(page))
    monkeypatch.setattr(page_cache, "is_stale", lambda page, ttl: True)
    monkeypatch.setattr(page_cache, "cache_age", lambda page: news_module.NEWS_MAX_STALENESS + 1)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module, "_can_request_news", lambda: False)

    client = _client()
    resp = client.get("/market/overview")

    assert resp.status_code == 200
    assert resp.json()["headlines"] == [{"headline": "Old headline", "url": "https://example.test/old", "stale": True}]


def test_market_overview_default_region_handles_fetch_failures(monkeypatch):
    client = _client()
    monkeypatch.setattr(market.cfg, "default_sector_region", "US", raising=False)
    calls = []

    def boom_indexes():
        calls.append("indexes")
        raise RuntimeError("boom indexes")

    def boom_sectors(region):
        assert region == "us"
        calls.append("sectors")
        raise RuntimeError("boom sectors")

    def boom_headlines():
        calls.append("headlines")
        raise RuntimeError("boom headlines")

    monkeypatch.setattr(market, "_fetch_indexes", boom_indexes)
    monkeypatch.setattr(market.market_sectors, "fetch_region_sectors", boom_sectors)
    monkeypatch.setattr(market, "_fetch_headlines", boom_headlines)

    resp = client.get("/market/overview")
    assert resp.status_code == 200
    assert resp.json() == {"indexes": {}, "sectors": [], "headlines": [], "headlines_status": "unavailable"}
    # Fetchers run concurrently on separate threads, so call order isn't
    # guaranteed - only that all three ran.
    assert set(calls) == {"indexes", "sectors", "headlines"}


def test_market_overview_uk_region_handles_fetch_errors(monkeypatch):
    client = _client()
    monkeypatch.setattr(market.cfg, "default_sector_region", "US", raising=False)

    monkeypatch.setattr(
        market,
        "_fetch_indexes",
        lambda: {"Dow Jones": {"value": 100.0, "change": 1.5}},
    )
    calls = []

    def boom_uk(region):
        calls.append(region)
        raise RuntimeError("boom uk")

    def boom_headlines():
        calls.append("headlines")
        raise RuntimeError("boom headlines")

    monkeypatch.setattr(market.market_sectors, "fetch_region_sectors", boom_uk)
    monkeypatch.setattr(market, "_fetch_headlines", boom_headlines)

    resp = client.get("/market/overview", params={"region": "UK"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexes"] == {"Dow Jones": {"value": 100.0, "change": 1.5}}
    assert data["sectors"] == []
    assert data["headlines"] == []
    # Fetchers run concurrently on separate threads, so call order isn't
    # guaranteed - only that both ran.
    assert set(calls) == {"uk", "headlines"}


def test_market_overview_fetchers_run_concurrently(monkeypatch):
    """The three fetchers must run at the same time, not one after another.

    Each fake fetcher waits on a 3-party barrier, which only releases once all
    three are inside a fetcher at once, so a sequential implementation times
    the barrier out. This checks overlap directly rather than wall-clock time,
    which flaked on loaded CI runners (#8695).
    """

    barrier = threading.Barrier(3, timeout=5)
    passed: list[str] = []

    def meet(name, result):
        def fetch():
            # _safe swallows exceptions, so a broken barrier would not fail the
            # request -- record who got through and assert on that instead.
            barrier.wait()
            passed.append(name)
            return result

        return fetch

    monkeypatch.setattr(market, "_fetch_indexes", meet("indexes", {}))
    sectors_fetch = meet("sectors", [])
    monkeypatch.setattr(market.market_sectors, "fetch_region_sectors", lambda _region: sectors_fetch())
    monkeypatch.setattr(market, "_fetch_headlines", meet("headlines", []))

    resp = _client().get("/market/overview")

    assert resp.status_code == 200
    assert sorted(passed) == ["headlines", "indexes", "sectors"], "fetchers did not overlap"


# ---------------------------------------------------------------------------
# Tests using unittest.mock.patch instead of monkeypatch
# ---------------------------------------------------------------------------


@patch("backend.routes.market._fetch_indexes", return_value={})
@patch("backend.common.market_sectors.fetch_region_sectors", return_value=[])
@patch("backend.routes.market._fetch_headlines", return_value=[])
def test_market_overview_returns_200(
    mock_headlines,
    mock_sectors,
    mock_indexes,
) -> None:
    """All three fetchers return empty data; endpoint responds 200 with expected keys."""
    client = _client()
    resp = client.get("/market/overview")
    assert resp.status_code == 200
    assert resp.json() == {"indexes": {}, "sectors": [], "headlines": [], "headlines_status": "unavailable"}


@patch(
    "backend.routes.market._fetch_indexes",
    return_value={"S&P 500": {"value": 5000.0, "change": 0.5}},
)
@patch(
    "backend.common.market_sectors.fetch_region_sectors",
    return_value=[{"sector": "Energy", "change": 1.2, "source": "basket"}],
)
@patch("backend.routes.market._fetch_headlines", return_value=[{"headline": "Markets rally"}])
def test_market_overview_uk_region(
    mock_headlines,
    mock_sectors,
    mock_indexes,
) -> None:
    """Passing region=uk fetches the UK sector registry."""
    client = _client()
    resp = client.get("/market/overview", params={"region": "uk"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexes"] == {"S&P 500": {"value": 5000.0, "change": 0.5}}
    assert data["sectors"] == [{"sector": "Energy", "change": 1.2, "source": "basket"}]
    assert data["headlines"] == [{"headline": "Markets rally"}]
    mock_sectors.assert_called_once_with("uk")


@patch("backend.routes.market._fetch_indexes", return_value={})
@patch("backend.common.market_sectors.fetch_region_sectors", return_value=[])
@patch("backend.routes.market._fetch_headlines", return_value=[])
def test_market_overview_unknown_region_falls_back_to_default(
    mock_headlines,
    mock_sectors,
    mock_indexes,
    monkeypatch,
) -> None:
    """Unlike /market/sectors, the overview tolerates an unknown region."""
    monkeypatch.setattr(market.cfg, "default_sector_region", "global", raising=False)
    resp = _client().get("/market/overview", params={"region": "mars"})
    assert resp.status_code == 200
    mock_sectors.assert_called_once_with("global")


@patch(
    "backend.routes.market._fetch_indexes",
    return_value={"S&P 500": {"value": 5000.0, "change": 0.5}},
)
@patch(
    "backend.common.market_sectors.fetch_region_sectors",
    return_value=[{"sector": "Energy", "change": -0.3, "source": "etf"}],
)
@patch("backend.routes.market._fetch_headlines", side_effect=Exception("headlines down"))
def test_market_overview_fetcher_exception_returns_default(
    mock_headlines,
    mock_sectors,
    mock_indexes,
) -> None:
    """When one fetcher raises, the endpoint still returns 200 with default values
    for the failing field and real data for the other fields (thanks to _safe)."""
    client = _client()
    resp = client.get("/market/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexes"] == {"S&P 500": {"value": 5000.0, "change": 0.5}}
    assert data["sectors"] == [{"sector": "Energy", "change": -0.3, "source": "etf"}]
    assert data["headlines"] == []
