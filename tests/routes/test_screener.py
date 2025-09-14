import asyncio

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from backend.routes import screener
from backend.screener import Fundamentals
from backend.utils import page_cache


def _client():
    app = FastAPI()
    app.include_router(screener.router)
    return TestClient(app)


def test_hash_params_stable_and_callable(monkeypatch):
    calls = []

    def fake_screen(symbols, **kwargs):
        calls.append((symbols, kwargs))
        return [Fundamentals(ticker=s) for s in symbols]

    monkeypatch.setattr(screener, "screen", fake_screen)

    kwargs = dict(
        peg_max=1,
        pe_max=None,
        de_max=None,
        lt_de_max=None,
        interest_coverage_min=None,
        current_ratio_min=None,
        quick_ratio_min=None,
        fcf_min=None,
        eps_min=None,
        gross_margin_min=None,
        operating_margin_min=None,
        net_margin_min=None,
        ebitda_margin_min=None,
        roa_min=None,
        roe_min=None,
        roi_min=None,
        dividend_yield_min=None,
        dividend_payout_ratio_max=None,
        beta_max=None,
        shares_outstanding_min=None,
        float_shares_min=None,
        market_cap_min=None,
        high_52w_max=None,
        low_52w_min=None,
        avg_volume_min=None,
    )

    page1, call1 = screener._hash_params(["AAA", "BBB"], **kwargs)
    page2, _ = screener._hash_params(["AAA", "BBB"], **kwargs)

    assert page1 == page2
    assert page1.startswith("screener_")
    result = call1()
    assert [r["ticker"] for r in result] == ["AAA", "BBB"]
    assert calls == [(["AAA", "BBB"], kwargs)]


def test_apply_rank_ties_and_nan():
    rows = [
        {"ticker": "A", "peg_ratio": 1, "roe": 1},
        {"ticker": "B", "peg_ratio": 2, "roe": 2},
        {"ticker": "C", "peg_ratio": float("nan"), "roe": 1},
        {"ticker": "D", "peg_ratio": 3, "roe": 0},
    ]

    screener._apply_rank(rows)

    assert [r["ticker"] for r in rows] == ["A", "B", "C", "D"]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]


def test_screener_success(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    saved = {}

    def fake_save(page, data):
        saved["page"] = page
        saved["data"] = data

    monkeypatch.setattr(page_cache, "save_cache", fake_save)

    def fake_screen(symbols, **kwargs):
        return [Fundamentals(ticker=symbols[0], peg_ratio=1, roe=2)]

    monkeypatch.setattr(screener, "screen", fake_screen)

    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["ticker"] == "ABC"
    assert data[0]["peg_ratio"] == 1
    assert data[0]["roe"] == 2
    assert data[0]["rank"] == 1
    assert saved["data"][0]["ticker"] == "ABC"


def test_screener_cached_path(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: False)
    monkeypatch.setattr(
        page_cache,
        "load_cache",
        lambda p: [{"ticker": "C", "peg_ratio": 1, "roe": 1}],
    )
    called = False

    def fake_screen(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(screener, "screen", fake_screen)

    resp = client.get("/screener", params={"tickers": "C"})
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["ticker"] == "C"
    assert data[0]["rank"] == 1
    assert not called


def test_screener_empty_tickers():
    client = _client()
    resp = client.get("/screener", params={"tickers": " , "})
    assert resp.status_code == 400


def test_screener_value_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)

    def fake_screen(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(screener, "screen", fake_screen)
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 400


def test_screener_runtime_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)

    def fake_screen(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(screener, "screen", fake_screen)
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 500


def test_background_tasks_scheduled(monkeypatch):
    bt = BackgroundTasks()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    saved = {}
    monkeypatch.setattr(page_cache, "save_cache", lambda p, d: saved.setdefault("data", d))
    monkeypatch.setattr(
        screener,
        "screen",
        lambda symbols, **k: [Fundamentals(ticker=symbols[0], peg_ratio=1, roe=1)],
    )

    result = asyncio.run(screener.screener(bt, tickers="ABC"))
    assert result[0]["ticker"] == "ABC"
    assert len(bt.tasks) == 1
    task = bt.tasks[0]
    assert task.func is page_cache.save_cache
    asyncio.run(bt())
    assert saved["data"][0]["ticker"] == "ABC"
