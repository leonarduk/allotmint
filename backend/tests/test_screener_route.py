from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import screener
from backend.utils import page_cache


def _client():
    app = FastAPI()
    app.include_router(screener.router)
    return TestClient(app)


def test_screener_success(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    saved = {}
    monkeypatch.setattr(page_cache, "save_cache", lambda p, d: saved.setdefault("data", d))

    monkeypatch.setattr(
        screener,
        "screen",
        lambda symbols, **k: [SimpleNamespace(model_dump=lambda: {"ticker": symbols[0]})],
    )
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "ABC"}]
    assert saved["data"] == [{"ticker": "ABC"}]


def test_screener_uses_cache(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: False)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: [{"ticker": "C"}])
    called = False

    def _screen(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(screener, "screen", _screen)
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "C"}]
    assert not called


def test_screener_no_tickers(monkeypatch):
    client = _client()
    resp = client.get("/screener", params={"tickers": " , "})
    assert resp.status_code == 400


def test_screener_value_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    monkeypatch.setattr(
        screener,
        "screen",
        lambda symbols, **k: (_ for _ in ()).throw(ValueError("bad")),
    )
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 400
