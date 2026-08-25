"""Route-level tests for ``GET /instrument/batch``.

Covers the input contract the domain helper does not own: parsing, de-duplication
before the cap, and the deliberate choice of ``400`` over silent truncation.
"""

import pytest
from fastapi.testclient import TestClient

import backend.common.instrument_api as ia
from backend.routes import instrument as instrument_route


@pytest.fixture
def client(mock_google_verify):
    from backend import config as backend_config

    previous = backend_config.offline_mode
    backend_config.offline_mode = True
    from backend.local_api.main import app

    c = TestClient(app)
    token = c.post("/token", json={"id_token": "good"}).json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {token}"})
    try:
        yield c
    finally:
        backend_config.offline_mode = previous


@pytest.fixture(autouse=True)
def stub_batch(monkeypatch):
    """Record what the route forwards, without touching the timeseries layer."""
    calls = {}

    def fake_batch(tickers, days=365, include_mini=False):
        calls["tickers"] = list(tickers)
        calls["days"] = days
        calls["include_mini"] = include_mini
        return {"instruments": {}, "empty": [], "unknown": list(tickers)}

    monkeypatch.setattr(ia, "batch_timeseries_for_tickers", fake_batch)
    return calls


def test_batch_forwards_parsed_tickers(client, stub_batch):
    res = client.get("/instrument/batch?tickers=AAA.L,BBB.L&days=30")

    assert res.status_code == 200
    assert stub_batch["tickers"] == ["AAA.L", "BBB.L"]
    assert stub_batch["days"] == 30
    assert stub_batch["include_mini"] is False


def test_batch_defaults_mini_off_and_window_to_365(client, stub_batch):
    client.get("/instrument/batch?tickers=AAA.L")

    assert stub_batch["days"] == 365
    assert stub_batch["include_mini"] is False


def test_batch_include_mini_opt_in(client, stub_batch):
    client.get("/instrument/batch?tickers=AAA.L&include_mini=true")

    assert stub_batch["include_mini"] is True


def test_batch_rejects_missing_tickers(client):
    # This app maps RequestValidationError on a bodyless request to 400, not
    # FastAPI's default 422 (backend/bootstrap/middleware.py).
    assert client.get("/instrument/batch").status_code == 400


def test_batch_rejects_blank_tickers(client):
    res = client.get("/instrument/batch?tickers=,,%20,")

    assert res.status_code == 400
    assert "at least one ticker" in res.json()["detail"]


def test_batch_rejects_over_cap_rather_than_truncating(client):
    """A truncated response would read as complete and leave holdings blank."""
    over = ",".join(f"T{i}.L" for i in range(instrument_route.MAX_BATCH_TICKERS + 1))

    res = client.get(f"/instrument/batch?tickers={over}")

    assert res.status_code == 400
    assert "Too many tickers" in res.json()["detail"]


def test_batch_cap_applies_after_dedupe(client, stub_batch):
    """Duplicates must not push an otherwise-valid request over the cap."""
    unique = [f"T{i}.L" for i in range(instrument_route.MAX_BATCH_TICKERS)]
    with_dupes = ",".join(unique + unique)

    res = client.get(f"/instrument/batch?tickers={with_dupes}")

    assert res.status_code == 200
    assert stub_batch["tickers"] == unique


def test_batch_rejects_non_positive_days(client):
    assert client.get("/instrument/batch?tickers=AAA.L&days=0").status_code == 400
