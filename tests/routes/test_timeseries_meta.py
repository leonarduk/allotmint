import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.config import config

# ---- Helper utilities -----------------------------------------------------

def _client_with_df(monkeypatch, df):
    """Return TestClient with ``load_meta_timeseries_range`` patched."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta, "load_meta_timeseries_range", lambda *a, **k: df.copy()
    )
    monkeypatch.setattr(ts_meta.pd, "to_datetime", lambda x: x)

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


# ---- _resolve_ticker_exchange tests ---------------------------------------


def test_resolve_with_provided_exchange():
    import backend.routes.timeseries_meta as ts_meta

    sym, ex = ts_meta._resolve_ticker_exchange("abc", "l")
    assert sym == "ABC"
    assert ex == "L"


def test_resolve_with_inferred_exchange(monkeypatch):
    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta.instrument_api,
        "_resolve_full_ticker",
        lambda t, latest: ("XYZ", "L"),
    )
    sym, ex = ts_meta._resolve_ticker_exchange("xyz", None)
    assert (sym, ex) == ("XYZ", "L")


def test_resolve_missing_ticker_error():
    from fastapi import HTTPException

    import backend.routes.timeseries_meta as ts_meta

    with pytest.raises(HTTPException):
        ts_meta._resolve_ticker_exchange("", "L")


def test_resolve_cannot_infer_exchange(monkeypatch):
    from fastapi import HTTPException

    import backend.routes.timeseries_meta as ts_meta

    monkeypatch.setattr(
        ts_meta.instrument_api, "_resolve_full_ticker", lambda t, latest: None
    )
    with pytest.raises(HTTPException):
        ts_meta._resolve_ticker_exchange("xyz", None)


# ---- /timeseries/meta route tests -----------------------------------------


def _sample_df():
    return pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 2.0,
                "Low": 0.5,
                "Close": 1.5,
                "Volume": 100,
            }
        ]
    )


@pytest.mark.parametrize("fmt", ["json", "csv", "html"])
def test_timeseries_meta_formats_with_scaling(fmt, monkeypatch):
    df = _sample_df()
    client = _client_with_df(monkeypatch, df)

    resp = client.get(
        f"/timeseries/meta?ticker=ABC&exchange=L&format={fmt}&scaling=2"
    )
    assert resp.status_code == 200

    if fmt == "json":
        data = resp.json()
        assert data["scaling"] == 2
        assert data["prices"][0]["Close"] == 3.0
    elif fmt == "csv":
        assert "Date,Open,High,Low,Close,Volume" in resp.text
        assert "3.0" in resp.text
    else:  # html
        assert "<table" in resp.text
        assert "Scaling:</strong> 2.0x" in resp.text
        assert "3.0" in resp.text


# ---- /timeseries/html route tests -----------------------------------------


def _html_client(monkeypatch, yahoo_result):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    def fake_fetch(*_args, **_kwargs):
        if isinstance(yahoo_result, Exception):
            raise yahoo_result
        return yahoo_result.copy()

    monkeypatch.setattr(ts_meta.fetch_timeseries, "fetch_yahoo_timeseries", fake_fetch)
    monkeypatch.setattr(ts_meta, "get_scaling_override", lambda *a, **k: 1)
    monkeypatch.setattr(ts_meta, "apply_scaling", lambda df, scale: df)

    from backend.app import create_app

    app = create_app()
    return TestClient(app)


def test_timeseries_html_success(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 1.5,
                "Low": 0.5,
                "Close": 1.2,
                "Volume": 100,
            }
        ]
    )
    client = _html_client(monkeypatch, df)
    resp = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert resp.status_code == 200
    assert "ABC Price History" in resp.text
    assert "1.20" in resp.text


def test_timeseries_html_fallback(monkeypatch):
    client = _html_client(monkeypatch, Exception("boom"))
    resp = client.get("/timeseries/html?ticker=ABC&period=1y&interval=1d")
    assert resp.status_code == 200
    assert "ABC Price History" in resp.text
    assert "0.00" in resp.text


# ---- /timeseries/meta date-range parameter tests --------------------------


def _multi_day_df():
    rows = [
        {"Date": "2024-01-01", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100},
        {"Date": "2024-01-02", "Open": 2.0, "High": 3.0, "Low": 1.0, "Close": 2.5, "Volume": 200},
        {"Date": "2024-01-03", "Open": 3.0, "High": 4.0, "Low": 2.0, "Close": 3.5, "Volume": 300},
    ]
    return pd.DataFrame(rows)


def test_explicit_start_and_end_date(monkeypatch):
    """Both dates supplied: response reflects the provided bounds."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-01&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from"] == "2024-01-01"
    assert data["to"] == "2024-01-03"


def test_open_start_only_end_date(monkeypatch):
    """Only end_date supplied: response uses end_date and days-derived start."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&end_date=2024-01-03"
    )
    assert resp.status_code == 200
    assert resp.json()["to"] == "2024-01-03"


def test_open_end_only_start_date(monkeypatch):
    """Only start_date supplied: response uses start_date and yesterday as end."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&start_date=2024-01-01"
    )
    assert resp.status_code == 200
    assert resp.json()["from"] == "2024-01-01"


def test_neither_date_param_uses_days(monkeypatch):
    """No date params: existing days-based behaviour is preserved (regression guard)."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get("/timeseries/meta?ticker=ABC&exchange=L&format=json&days=365")
    assert resp.status_code == 200
    data = resp.json()
    assert "from" in data and "to" in data


def test_invalid_range_returns_422(monkeypatch):
    """start_date after end_date must return HTTP 422."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json"
        "&start_date=2024-01-10&end_date=2024-01-01"
    )
    assert resp.status_code == 422


def test_malformed_date_returns_4xx(monkeypatch):
    """A non-ISO date string must be rejected (400 or 422)."""
    client = _client_with_df(monkeypatch, _multi_day_df())
    resp = client.get(
        "/timeseries/meta?ticker=ABC&exchange=L&format=json&start_date=not-a-date"
    )
    assert resp.status_code in (400, 422)

