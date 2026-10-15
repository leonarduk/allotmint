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


def _download_frame(
    closes: dict[str, list[float]], index: pd.DatetimeIndex, dividends: dict[tuple[str, int], float] | None = None
) -> pd.DataFrame:
    columns = pd.MultiIndex.from_product([["Close"], list(closes)], names=["Price", "Ticker"])
    rows = list(zip(*closes.values(), strict=True))
    frame = pd.DataFrame(rows, columns=columns, index=index)
    if dividends:
        paid = pd.DataFrame(0.0, index=index, columns=pd.MultiIndex.from_product([["Dividends"], list(closes)]))
        for (symbol, row), amount in dividends.items():
            paid.iloc[row, paid.columns.get_loc(("Dividends", symbol))] = amount
        frame = pd.concat([frame, paid], axis=1)
    return frame


def _only(monkeypatch, *names: str) -> None:
    """Limit the benchmark rows to ``names``, keeping their real symbols."""

    monkeypatch.setattr(market, "BENCHMARKS", tuple(b for b in market.BENCHMARKS if b.name in names))


@pytest.fixture(autouse=True)
def _fresh_cache():
    market._BENCHMARK_CACHE.clear()
    yield
    market._BENCHMARK_CACHE.clear()


def test_index_summary_reports_points_and_pct_per_window(monkeypatch):
    # Daily calendar closes over 400 days: 1000 -> 1399, so every window has a base.
    index = pd.date_range("2025-01-01", periods=400, freq="D")
    rising = [1000.0 + i for i in range(400)]
    _only(monkeypatch, "FTSE 100")
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: _download_frame({"^FTSE": rising}, index))

    body = _client().get("/market/index-summary").json()

    [row] = body["indexes"]
    assert row["name"] == "FTSE 100"
    assert row["symbol"] == "^FTSE"
    assert row["currency"] == "GBP"
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
    _only(monkeypatch, "FTSE 250")
    monkeypatch.setattr(
        market_sectors.yf, "download", lambda *_, **__: _download_frame({"^FTMC": [20000.0] * 10}, index)
    )

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1W"] == {"change": 0.0, "pct": 0.0, "local_pct": 0.0}
    assert row["changes"]["1M"] is None
    assert row["changes"]["1Y"] is None


def test_index_summary_treats_a_zero_base_close_as_no_data(monkeypatch):
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    _only(monkeypatch, "NASDAQ-100")
    monkeypatch.setattr(
        market_sectors.yf, "download", lambda *_, **__: _download_frame({"^NDX": [5.0, 0.0, 3.0]}, index)
    )

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1D"] is None


def test_index_summary_skips_indices_without_closes(monkeypatch):
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    _only(monkeypatch, "FTSE 100", "NASDAQ-100")
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

    _only(monkeypatch, "S&P 500")
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


FLAT_YEAR = pd.date_range("2025-01-01", periods=400, freq="D")


def test_index_summary_reinvests_etf_proxy_dividends_for_total_return(monkeypatch):
    # Flat index and ETF; one 5p dividend inside the year is the whole total return.
    _only(monkeypatch, "FTSE 100")
    frame = _download_frame({"^FTSE": [8000.0] * 400, "ISF.L": [100.0] * 400}, FLAT_YEAR, {("ISF.L", 200): 5.0})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1Y"]["pct"] == pytest.approx(0.0)
    assert row["total_return_1y"] == {
        "pct": pytest.approx(5.0),
        "symbol": "ISF.L",
        "source": "etf",
        "local_currency": "GBP",
        "local_pct": pytest.approx(5.0),
    }


def test_index_summary_converts_a_usd_total_return_to_gbp(monkeypatch):
    # 11.5% in USD while the dollar rises 10% against sterling: 1.115 * 1.1 - 1 in GBP.
    _only(monkeypatch, "S&P 500")
    price = [1000.0] * 399 + [1100.0]
    total_return = [1000.0] * 399 + [1115.0]
    gbp_per_usd = [0.80] * 399 + [0.88]
    frame = _download_frame({"^GSPC": price, "^SP500TR": total_return, "USDGBP=X": gbp_per_usd}, FLAT_YEAR)
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    # Points stay index points; the % is in GBP, with the USD move beside it.
    assert row["changes"]["1Y"] == {
        "change": pytest.approx(100.0),
        "pct": pytest.approx(21.0),
        "local_pct": pytest.approx(10.0),
    }
    assert row["total_return_1y"] == {
        "pct": pytest.approx(22.65),
        "symbol": "^SP500TR",
        "source": "index",
        "local_currency": "USD",
        "local_pct": pytest.approx(11.5),
    }


def test_gbp_conversion_carries_the_last_rate_over_missing_fx_days(monkeypatch):
    # No FX print on the final index day: the previous day's rate applies.
    _only(monkeypatch, "NASDAQ-100")
    gbp_per_usd = [0.80] * 398 + [0.88, float("nan")]
    frame = _download_frame(
        {"^NDX": [100.0] * 399 + [108.0], "QQQ": [100.0] * 399 + [110.0], "USDGBP=X": gbp_per_usd}, FLAT_YEAR
    )
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["total_return_1y"]["local_pct"] == pytest.approx(10.0)
    assert row["total_return_1y"]["pct"] == pytest.approx(21.0)


def test_index_summary_has_no_usd_total_return_without_an_fx_rate(monkeypatch):
    # Showing the USD figure as if it were sterling would be wrong, so none is shown.
    _only(monkeypatch, "S&P 500")
    frame = _download_frame({"^GSPC": [1000.0] * 400, "^SP500TR": [1000.0] * 399 + [1015.0]}, FLAT_YEAR)
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["total_return_1y"] is None


def test_usd_price_change_has_no_gbp_pct_without_an_fx_rate(monkeypatch):
    _only(monkeypatch, "NASDAQ-100")
    frame = _download_frame({"^NDX": [100.0] * 399 + [110.0]}, FLAT_YEAR)
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1Y"] == {"change": pytest.approx(10.0), "pct": None, "local_pct": pytest.approx(10.0)}


def test_plausibility_band_ignores_the_fx_move(monkeypatch):
    # A 20% sterling move is far outside the dividend band, but the band is
    # judged in USD, where the total return is only 1.5pp above price.
    _only(monkeypatch, "S&P 500")
    frame = _download_frame(
        {
            "^GSPC": [1000.0] * 400,
            "^SP500TR": [1000.0] * 399 + [1015.0],
            "USDGBP=X": [0.80] * 399 + [0.96],
        },
        FLAT_YEAR,
    )
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["total_return_1y"]["pct"] == pytest.approx(21.8)


def test_index_summary_downloads_fx_with_the_indices(monkeypatch):
    requested = []
    index = FLAT_YEAR[:3]

    def fake_download(symbols, *_args, **_kwargs):
        requested.append(list(symbols))
        return _download_frame({"^GSPC": [1.0, 2.0, 3.0]}, index)

    _only(monkeypatch, "S&P 500")
    monkeypatch.setattr(market_sectors.yf, "download", fake_download)

    _client().get("/market/index-summary")

    assert requested == [["^GSPC", "^SP500TR", "USDGBP=X"]]


def test_total_return_frame_keeps_a_symbol_without_dividends():
    # ^SP500TR pays nothing itself, so its total-return series must be its closes.
    frame = _download_frame({"^SP500TR": [1.0, 2.0, 3.0], "ISF.L": [100.0] * 3}, FLAT_YEAR[:3], {("ISF.L", 2): 1.0})
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)
        history = market_sectors.download_period_history(["^SP500TR", "ISF.L"], "1Y")

    assert list(market_sectors.series_for(history.total_return, "^SP500TR")) == [1.0, 2.0, 3.0]


def test_index_summary_drops_an_implausible_total_return(monkeypatch):
    # A dividend in pounds against pence closes would add ~100x too much (#10742).
    _only(monkeypatch, "FTSE 250")
    frame = _download_frame({"^FTMC": [20000.0] * 400, "MIDD.L": [100.0] * 400}, FLAT_YEAR, {("MIDD.L", 200): 50.0})
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["changes"]["1Y"]["pct"] == pytest.approx(0.0)
    assert row["total_return_1y"] is None


def test_index_summary_has_no_total_return_without_the_source(monkeypatch):
    _only(monkeypatch, "NASDAQ-100")
    frame = _download_frame({"^NDX": [20000.0] * 400}, FLAT_YEAR)
    monkeypatch.setattr(market_sectors.yf, "download", lambda *_, **__: frame)

    [row] = _client().get("/market/index-summary").json()["indexes"]

    assert row["symbol"] == "^NDX"
    assert row["total_return_1y"] is None
