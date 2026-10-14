"""Tests for the benchmark index rows beside the owner summary table."""

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


def _download_frame(closes: dict[str, list[float]], index: pd.DatetimeIndex) -> pd.DataFrame:
    columns = pd.MultiIndex.from_product([["Close"], list(closes)], names=["Price", "Ticker"])
    rows = list(zip(*closes.values(), strict=True))
    return pd.DataFrame(rows, columns=columns, index=index)


@pytest.fixture(autouse=True)
def _fresh_cache():
    market._BENCHMARK_CACHE.clear()
    yield
    market._BENCHMARK_CACHE.clear()


def test_index_summary_reports_points_and_pct_per_window(monkeypatch):
    # Daily calendar closes over 400 days: 1000 -> 1399, so every window has a base.
    index = pd.date_range("2025-01-01", periods=400, freq="D")
    rising = [1000.0 + i for i in range(400)]
    monkeypatch.setattr(market, "BENCHMARK_INDEX_NAMES", ("FTSE 100",))
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: _download_frame({"^FTSE": rising}, index))

    body = _client().get("/market/index-summary").json()

    [row] = body["indexes"]
    assert row["name"] == "FTSE 100"
    assert row["symbol"] == "^FTSE"
    assert row["value"] == 1399.0
    assert row["as_of"].startswith("2026-02-04")
    changes = row["changes"]
    assert changes["1D"]["change"] == pytest.approx(1.0)
    assert changes["1D"]["pct"] == pytest.approx(1 / 1398 * 100)
    assert changes["1W"]["change"] == pytest.approx(7.0)
    assert changes["1M"]["change"] == pytest.approx(30.0)
    assert changes["1Y"]["change"] == pytest.approx(365.0)
    assert changes["1Y"]["pct"] == pytest.approx(365 / 1034 * 100)


def test_index_summary_marks_short_history_windows_as_none(monkeypatch):
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    monkeypatch.setattr(market, "BENCHMARK_INDEX_NAMES", ("FTSE 250",))
    monkeypatch.setattr(
        market_sectors.yf, "download", lambda *_, **__: _download_frame({"^FTMC": [20000.0] * 10}, index)
    )

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1W"] == {"change": 0.0, "pct": 0.0}
    assert row["changes"]["1M"] is None
    assert row["changes"]["1Y"] is None


def test_index_summary_treats_a_zero_base_close_as_no_data(monkeypatch):
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    monkeypatch.setattr(market, "BENCHMARK_INDEX_NAMES", ("NASDAQ",))
    monkeypatch.setattr(
        market_sectors.yf, "download", lambda *_, **__: _download_frame({"^IXIC": [5.0, 0.0, 3.0]}, index)
    )

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1D"] is None


def test_index_summary_skips_indices_without_closes(monkeypatch):
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    monkeypatch.setattr(market, "BENCHMARK_INDEX_NAMES", ("FTSE 100", "NASDAQ"))
    monkeypatch.setattr(
        market_sectors.yf, "download", lambda *_, **__: _download_frame({"^FTSE": [1.0, 2.0, 3.0]}, index)
    )

    names = [row["name"] for row in _client().get("/market/index-summary").json()["indexes"]]

    assert names == ["FTSE 100"]


def test_index_summary_is_cached_between_requests(monkeypatch):
    calls = []
    index = pd.date_range("2026-01-01", periods=3, freq="D")

    def fake_download(*_args, **_kwargs):
        calls.append(1)
        return _download_frame({"^GSPC": [1.0, 2.0, 3.0]}, index)

    monkeypatch.setattr(market, "BENCHMARK_INDEX_NAMES", ("S&P 500",))
    monkeypatch.setattr(market_sectors.yf, "download", fake_download)

    client = _client()
    client.get("/market/index-summary")
    client.get("/market/index-summary")

    assert len(calls) == 1


def test_index_summary_returns_502_when_download_fails(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(market_sectors.yf, "download", boom)

    response = _client().get("/market/index-summary")

    assert response.status_code == 502


def test_benchmark_names_are_known_index_symbols():
    assert set(market.BENCHMARK_INDEX_NAMES) <= set(market.INDEX_SYMBOLS)
