import pandas as pd
from fastapi.testclient import TestClient

from backend.config import config


def _client(monkeypatch, cached: dict[tuple[str, str], pd.DataFrame]):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.data_quality as data_quality_route

    monkeypatch.setattr(data_quality_route, "list_cached_meta_tickers", lambda: sorted(cached.keys()))
    monkeypatch.setattr(
        data_quality_route,
        "has_cached_meta_timeseries",
        lambda ticker, exchange: (ticker, exchange) in cached,
    )
    monkeypatch.setattr(
        data_quality_route,
        "load_cached_meta_timeseries_full",
        lambda ticker, exchange: cached[(ticker, exchange)].copy(),
    )

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


def _clean_df():
    return pd.DataFrame([{"Date": f"2026-01-{d:02d}", "Close": 100.0} for d in (5, 6, 7, 8, 9)])


def test_lists_quality_for_all_cached_tickers(monkeypatch):
    cached = {("ABC", "L"): _clean_df(), ("XYZ", "N"): _clean_df()}
    client = _client(monkeypatch, cached)
    resp = client.get("/data-quality/timeseries")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["truncated"] is False
    tickers = {(p["ticker"], p["exchange"]) for p in data["positions"]}
    assert tickers == {("ABC", "L"), ("XYZ", "N")}


def test_max_results_limits_pairs_and_sets_truncated(monkeypatch):
    cached = {("ABC", "L"): _clean_df(), ("XYZ", "N"): _clean_df()}
    client = _client(monkeypatch, cached)
    resp = client.get("/data-quality/timeseries?max_results=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["truncated"] is True


def test_max_results_larger_than_total_is_not_truncated(monkeypatch):
    cached = {("ABC", "L"): _clean_df(), ("XYZ", "N"): _clean_df()}
    client = _client(monkeypatch, cached)
    resp = client.get("/data-quality/timeseries?max_results=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["truncated"] is False


def test_max_results_out_of_range_rejected(monkeypatch):
    client = _client(monkeypatch, {})
    resp = client.get("/data-quality/timeseries?max_results=0")
    assert resp.status_code == 400


def test_filters_to_single_ticker(monkeypatch):
    cached = {("ABC", "L"): _clean_df(), ("XYZ", "N"): _clean_df()}
    client = _client(monkeypatch, cached)
    resp = client.get("/data-quality/timeseries?ticker=abc&exchange=l")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["positions"][0]["ticker"] == "ABC"


def test_unknown_ticker_returns_404(monkeypatch):
    client = _client(monkeypatch, {})
    resp = client.get("/data-quality/timeseries?ticker=ABC&exchange=L")
    assert resp.status_code == 404


def test_ticker_without_exchange_is_bad_request(monkeypatch):
    client = _client(monkeypatch, {})
    resp = client.get("/data-quality/timeseries?ticker=ABC")
    assert resp.status_code == 400


def test_invalid_ticker_format_rejected(monkeypatch):
    client = _client(monkeypatch, {})
    resp = client.get(
        "/data-quality/timeseries",
        params={"ticker": "<script>alert(1)</script>", "exchange": "L"},
    )
    assert resp.status_code == 400
    assert "<script>" not in resp.text.lower()


def test_reports_gap_and_duplicate_metrics(monkeypatch):
    df = pd.DataFrame(
        [
            {"Date": "2026-01-05", "Close": 100.0},
            {"Date": "2026-01-05", "Close": 101.0},  # duplicate date
            {"Date": "2026-01-12", "Close": 100.0},  # gap over 6th-9th
        ]
    )
    client = _client(monkeypatch, {("ABC", "L"): df})
    resp = client.get("/data-quality/timeseries?ticker=ABC&exchange=L")
    assert resp.status_code == 200
    position = resp.json()["positions"][0]
    assert position["duplicate_dates"] == ["2026-01-05"]
    assert position["gap_count"] == 1
    assert position["gaps"][0]["missing_business_days"] == 4


def test_response_never_returned_for_write_methods(monkeypatch):
    client = _client(monkeypatch, {("ABC", "L"): _clean_df()})
    resp = client.post("/data-quality/timeseries")
    assert resp.status_code == 405
