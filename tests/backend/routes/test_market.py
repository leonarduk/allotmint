from __future__ import annotations

from typing import List

from backend.routes import market as market_module


def _make_payload(symbol: str, label: str) -> List[dict[str, str]]:
    return [{"headline": f"{symbol} {label}", "url": f"https://example.com/{symbol.lower()}"}]


def test_fetch_headlines_uses_cached_helper(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())
    seen_fresh: set[str] = set()

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        if symbol in seen_fresh:
            return _make_payload(symbol, "cached")
        seen_fresh.add(symbol)
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    first = market_module._fetch_headlines()
    second = market_module._fetch_headlines()

    assert seen_fresh == set(symbols)
    assert sorted(item["headline"] for item in first) == sorted(
        f"{sym} fresh" for sym in symbols
    )
    assert sorted(item["headline"] for item in second) == sorted(
        f"{sym} cached" for sym in symbols
    )


def test_fetch_headlines_stops_on_quota_exhaustion(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())
    stop_after = symbols[2]
    calls: list[str] = []

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        calls.append(symbol)
        if symbol == stop_after:
            raise RuntimeError("news quota exceeded")
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    headlines = market_module._fetch_headlines()

    assert calls == symbols[: symbols.index(stop_after) + 1]
    assert all(stop_after not in item["headline"] for item in headlines)
    assert all(
        item["headline"].endswith("fresh")
        for item in headlines
    )
