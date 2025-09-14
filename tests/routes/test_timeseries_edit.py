import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.routes import timeseries_edit
from backend.timeseries import cache


@pytest.mark.parametrize(
    "ticker,exchange,expected",
    [
        ("abc", "l", ("ABC", "L")),
        ("abc.l", None, ("ABC", "L")),
    ],
)
def test_resolve_ticker_exchange_direct(ticker, exchange, expected):
    assert timeseries_edit._resolve_ticker_exchange(ticker, exchange) == expected


def test_resolve_ticker_exchange_inferred(monkeypatch):
    def fake_resolve(t, latest):
        assert t == "ABC"
        return ("ABC", "L")

    monkeypatch.setattr(timeseries_edit.instrument_api, "_resolve_full_ticker", fake_resolve)
    monkeypatch.setattr(timeseries_edit.instrument_api, "_LATEST_PRICES", {})

    assert timeseries_edit._resolve_ticker_exchange("abc", None) == ("ABC", "L")


def test_resolve_ticker_exchange_error(monkeypatch):
    monkeypatch.setattr(timeseries_edit.instrument_api, "_resolve_full_ticker", lambda *_: None)
    monkeypatch.setattr(timeseries_edit.instrument_api, "_LATEST_PRICES", {})

    with pytest.raises(HTTPException) as exc:
        timeseries_edit._resolve_ticker_exchange("abc", None)
    assert exc.value.status_code == 400
    assert "could not be inferred" in exc.value.detail


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    app = FastAPI()
    app.include_router(timeseries_edit.router)
    return TestClient(app)


def test_post_json_and_get_format(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    data = [
        {"Date": "2024-01-01", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100},
        {"Date": "2024-01-02", "Open": 1.1, "High": 2.1, "Low": 0.6, "Close": 1.6, "Volume": 110},
    ]
    resp = client.post("/timeseries/edit?ticker=ABC&exchange=L", json=data)
    assert resp.status_code == 200
    assert resp.json()["rows"] == 2

    path = timeseries_edit.meta_timeseries_cache_path("ABC", "L")
    df = pd.read_parquet(path)
    assert len(df) == 2
    assert list(df["Ticker"]) == ["ABC", "ABC"]

    resp = client.get("/timeseries/edit?ticker=ABC&exchange=L")
    assert resp.status_code == 200
    returned = resp.json()
    assert returned[0]["Date"] == "2024-01-01"


def test_post_csv_saves_parquet(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)

    csv_data = "Date,Open,High,Low,Close,Volume\n2024-01-01,1,2,0.5,1.5,100\n2024-01-02,1.1,2.1,0.6,1.6,110\n"
    headers = {"Content-Type": "text/csv"}
    resp = client.post(
        "/timeseries/edit?ticker=XYZ&exchange=L",
        data=csv_data,
        headers=headers,
    )
    assert resp.status_code == 200
    path = timeseries_edit.meta_timeseries_cache_path("XYZ", "L")
    df = pd.read_parquet(path)
    assert df.loc[0, "Close"] == 1.5


def test_get_missing_file(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/timeseries/edit?ticker=NOPE&exchange=L")
    assert resp.status_code == 200
    assert resp.json() == []
