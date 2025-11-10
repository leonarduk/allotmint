from __future__ import annotations

import json

from backend.common import instruments


def _reset_state(monkeypatch, tmp_path):
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.setattr(instruments, "_AUTO_CREATE_FAILURES", set())
    instruments.get_instrument_meta.cache_clear()


def test_get_instrument_meta_auto_creates_using_yahoo(tmp_path, monkeypatch):
    _reset_state(monkeypatch, tmp_path)

    fetched = {
        "name": "Apple Inc.",
        "currency": "USD",
        "sector": "Technology",
        "region": "United States",
        "asset_class": "Equity",
        "instrument_type": "EQUITY",
    }

    calls: list[tuple[str, str]] = []

    def fake_fetch(symbol: str, exchange: str):
        calls.append((symbol, exchange))
        return dict(fetched)

    monkeypatch.setattr(instruments, "_fetch_metadata_from_yahoo", fake_fetch)

    meta = instruments.get_instrument_meta("aapl.n")

    assert meta["ticker"] == "AAPL.N"
    assert meta["name"] == fetched["name"]
    assert meta["currency"] == fetched["currency"]
    assert meta["sector"] == fetched["sector"]
    assert calls == [("AAPL", "N")]

    path = tmp_path / "N" / "AAPL.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["ticker"] == "AAPL.N"
    assert saved["name"] == fetched["name"]
    assert saved["currency"] == fetched["currency"]
    assert saved["sector"] == fetched["sector"]


def test_auto_create_skips_when_fetch_fails(tmp_path, monkeypatch):
    _reset_state(monkeypatch, tmp_path)

    calls = 0

    def fake_fetch(symbol: str, exchange: str):
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(instruments, "_fetch_metadata_from_yahoo", fake_fetch)

    meta = instruments.get_instrument_meta("MISS.N")
    assert meta == {}
    assert "MISS.N" in instruments._AUTO_CREATE_FAILURES
    assert calls == 1
    assert not list(tmp_path.rglob("*.json"))

    instruments.get_instrument_meta.cache_clear()
    meta_again = instruments.get_instrument_meta("MISS.N")
    assert meta_again == {}
    assert calls == 1  # failure cached, no retry


def test_auto_create_requires_exchange(tmp_path, monkeypatch):
    _reset_state(monkeypatch, tmp_path)

    calls: list[tuple[str, str]] = []

    def fake_fetch(symbol: str, exchange: str):  # pragma: no cover - should not be called
        calls.append((symbol, exchange))
        return {"name": "Should not happen"}

    monkeypatch.setattr(instruments, "_fetch_metadata_from_yahoo", fake_fetch)

    meta = instruments.get_instrument_meta("PFE")
    assert meta == {}
    assert calls == []
    assert not list(tmp_path.rglob("*.json"))
