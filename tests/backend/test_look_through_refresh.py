"""Refreshing one fund's look-through data on demand (#9974). No network access."""

import json

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.instrument_admin as instrument_admin
from backend.common import instruments, look_through
from backend.common.look_through_sources import LookThroughFetchError

BLOCK = {
    "source": "morningstar",
    "source_id": "0P0000WA5N",
    "as_of": "2026-08-31",
    "fetched": "2026-10-07",
    "countries": {"United States": 60.0, "Japan": 40.0},
    "sectors": {"Information Technology": 100.0},
    "top_holdings": [],
}


@pytest.fixture
def instruments_dir(tmp_path, monkeypatch):
    root = tmp_path / "instruments"
    (root / "L").mkdir(parents=True)
    meta = {"ticker": "VWRL.L", "name": "All-World", "instrumentType": "ETF", "isin": "IE00B3RBWM25"}
    (root / "L" / "VWRL.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", root)
    monkeypatch.setattr(instruments, "_s3_location", lambda: None)
    instruments.get_instrument_meta.cache_clear()
    yield root
    instruments.get_instrument_meta.cache_clear()


def test_refresh_stores_block_keeping_key_order(instruments_dir, monkeypatch):
    monkeypatch.setattr(look_through, "fetch_look_through", lambda isin: dict(BLOCK))

    result = look_through.refresh_instrument_look_through("VWRL.L")

    assert result["updated"] is True
    alloc = result["allocation"]
    assert alloc["kind"] == "fund"
    assert alloc["fetched"] == "2026-10-07"
    assert alloc["source_url"] == "https://global.morningstar.com/en-gb/search?query=IE00B3RBWM25"
    stored = json.loads((instruments_dir / "L" / "VWRL.json").read_text(encoding="utf-8"))
    assert list(stored) == ["ticker", "name", "instrumentType", "isin", "look_through"]


def test_refresh_without_coverage_leaves_file_alone(instruments_dir, monkeypatch):
    before = (instruments_dir / "L" / "VWRL.json").read_text(encoding="utf-8")
    monkeypatch.setattr(look_through, "fetch_look_through", lambda isin: None)

    result = look_through.refresh_instrument_look_through("VWRL.L")

    assert result["updated"] is False
    assert result["allocation"]["kind"] == "fund_uncovered"
    assert (instruments_dir / "L" / "VWRL.json").read_text(encoding="utf-8") == before


def test_refresh_needs_metadata_and_isin(monkeypatch):
    monkeypatch.setattr(look_through, "get_instrument_meta", lambda t: {"name": "No ISIN"} if t == "X.L" else {})
    with pytest.raises(look_through.LookThroughRefreshError):
        look_through.refresh_instrument_look_through("X.L")
    with pytest.raises(look_through.LookThroughRefreshError):
        look_through.refresh_instrument_look_through("MISSING.L")


def _client(monkeypatch, meta=None, refresh=None):
    app = FastAPI()
    app.include_router(instrument_admin.router)
    monkeypatch.setattr(instrument_admin.config, "offline_mode", False)
    monkeypatch.setattr(instrument_admin, "get_instrument_meta", lambda t: meta if meta is not None else {"isin": "X"})
    if refresh is not None:
        monkeypatch.setattr(instrument_admin.look_through, "refresh_instrument_look_through", refresh)
    return TestClient(app)


def test_route_returns_refreshed_allocation(monkeypatch):
    seen = []
    client = _client(monkeypatch, refresh=lambda t: seen.append(t) or {"updated": True, "allocation": {"ticker": t}})

    resp = client.post("/instrument/admin/L/vwrl/look-through")

    assert resp.status_code == 200
    assert resp.json() == {"updated": True, "allocation": {"ticker": "VWRL.L"}}
    assert seen == ["VWRL.L"]


@pytest.mark.parametrize(
    "error, status",
    [
        (look_through.LookThroughRefreshError("no ISIN"), 422),
        (LookThroughFetchError("HTTP 403"), 502),
        (requests.ConnectionError("down"), 502),
    ],
)
def test_route_maps_errors(monkeypatch, error, status):
    def _boom(_t):
        raise error

    assert _client(monkeypatch, refresh=_boom).post("/instrument/admin/L/VWRL/look-through").status_code == status


def test_route_unknown_instrument_and_offline(monkeypatch):
    assert _client(monkeypatch, meta={}).post("/instrument/admin/L/NOPE/look-through").status_code == 404
    client = _client(monkeypatch)
    monkeypatch.setattr(instrument_admin.config, "offline_mode", True)
    assert client.post("/instrument/admin/L/VWRL/look-through").status_code == 503
