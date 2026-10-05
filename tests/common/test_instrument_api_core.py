import time

import pytest

from backend.common import instrument_api as ia


def test_resolve_full_ticker_variants(monkeypatch):
    """Tickers with/without exchanges and unknown symbols."""
    monkeypatch.setattr(ia, "_TICKER_EXCHANGE_MAP", {"BAR": "L"})
    latest = {"FOO.L": 1.0}
    assert ia._resolve_full_ticker("foo.l", {}) == ("FOO", "L")
    assert ia._resolve_full_ticker("foo", latest) == ("FOO", "L")
    assert ia._resolve_full_ticker("bar", {}) == ("BAR", "L")
    assert ia._resolve_full_ticker("baz", {}) is None
    assert ia._resolve_full_ticker("", latest) is None


def test_prime_latest_prices_respects_skip(monkeypatch):
    monkeypatch.setattr(ia.config, "skip_snapshot_warm", True)
    called = {"v": False}

    def fake_load(_):
        called["v"] = True
        return {"AAA": 1.0}

    monkeypatch.setattr(ia, "load_latest_prices", fake_load)
    ia._LATEST_PRICES = {"OLD": 2.0}
    ia.prime_latest_prices()
    assert ia._LATEST_PRICES == {}
    assert called["v"] is False


def test_prime_latest_prices_populates(monkeypatch):
    monkeypatch.setattr(ia.config, "skip_snapshot_warm", False)
    monkeypatch.setattr(ia, "_ALL_TICKERS", ["AAA", "BBB"])

    def fake_load(tickers):
        assert tickers == ["AAA", "BBB"]
        return {"AAA": 1.23}

    monkeypatch.setattr(ia, "load_latest_prices", fake_load)
    ia._LATEST_PRICES = {}
    ia.prime_latest_prices()
    assert ia._LATEST_PRICES == {"AAA": 1.23}


def test_price_and_changes_unresolved(monkeypatch):
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: None)
    ia._price_and_changes.cache_clear()
    res = ia._price_and_changes("FOO")
    assert res["last_price_gbp"] is None
    assert res["is_stale"] is True


def test_price_and_changes_snapshot(monkeypatch):
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("ABC", "L"))
    monkeypatch.setattr(ia, "price_change_pct", lambda t, d: 1.0)
    from backend.common import portfolio_utils as pu

    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {"ABC": {"last_price": 123.0, "last_price_time": "2024-01-01T00:00:00", "is_stale": False}},
    )
    ia._price_and_changes.cache_clear()
    res = ia._price_and_changes("ABC")
    assert res["last_price_gbp"] == 123.0
    assert res["last_price_time"] == "2024-01-01T00:00:00"
    assert res["is_stale"] is False


def test_price_and_changes_fallback(monkeypatch):
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, loc: ("ABC", "L"))
    monkeypatch.setattr(ia, "price_change_pct", lambda t, d: 2.0)
    from backend.common import portfolio_utils as pu

    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(ia, "_close_on", lambda s, e, d: 50.0)
    ia._price_and_changes.cache_clear()
    res = ia._price_and_changes("ABC")
    assert res["last_price_gbp"] == 50.0
    assert res["last_price_time"] is None
    assert res["is_stale"] is True


def test_positions_for_ticker_matches(monkeypatch):
    gp = {
        "accounts": [
            {
                "owner": "Alice",
                "account_type": "isa",
                "currency": "GBP",
                "holdings": [
                    {
                        "ticker": "ABC.L",
                        "units": 10,
                        "current_price_gbp": 2.0,
                        "market_value_gbp": 20.0,
                        "cost_basis_gbp": 15.0,
                        "effective_cost_basis_gbp": 15.0,
                        "gain_gbp": 5.0,
                        "gain_pct": 10.0,
                        "days_held": 30,
                        "sell_eligible": True,
                        "days_until_eligible": 0,
                        "eligible_on": "2024-01-01",
                        "next_eligible_sell_date": "2024-01-01",
                    },
                    {"ticker": "XYZ.L", "units": 0},
                ],
            }
        ]
    }
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: gp)
    rows = ia.positions_for_ticker("grp", "ABC")
    assert rows == [
        {
            "owner": "Alice",
            "account_type": "isa",
            "currency": "GBP",
            "units": 10,
            "current_price_gbp": 2.0,
            "market_value_gbp": 20.0,
            "book_cost_basis_gbp": 15.0,
            "effective_cost_basis_gbp": 15.0,
            "gain_gbp": 5.0,
            "gain_pct": 10.0,
            "days_held": 30,
            "sell_eligible": True,
            "days_until_eligible": 0,
            "eligible_on": "2024-01-01",
            "next_eligible_sell_date": "2024-01-01",
        }
    ]


def test_build_exchange_map_uses_metadata(monkeypatch):
    monkeypatch.setattr(
        ia,
        "get_security_meta",
        lambda t: {"exchange": "L"} if t == "ABC" else {},
    )
    result = ia._build_exchange_map(["ABC", "DEF"])
    assert result == {"ABC": "L"}


def test_instrument_summaries_populate_grouping(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA.L", "name": "Alpha", "units": 1.0, "market_value_gbp": 100.0, "gain_gbp": 10.0},
                    {"ticker": "BBB.L", "name": "Beta", "units": 2.0, "market_value_gbp": 50.0, "gain_gbp": 5.0},
                    {"ticker": "CCC.L", "name": "Gamma", "units": 3.0, "market_value_gbp": 25.0, "gain_gbp": 2.5},
                ]
            }
        ]
    }

    meta = {
        "AAA.L": {"grouping": "Explicit"},
        "BBB.L": {"sector": "Sector B"},
        "CCC.L": {"region": "Region C"},
    }

    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: portfolio)
    monkeypatch.setattr(ia, "get_security_meta", lambda t: meta.get(t, {}))

    def fake_price_and_changes(ticker: str) -> dict:
        return {
            "last_price_gbp": 0.0,
            "last_price_date": "2024-01-01",
            "last_price_time": None,
            "is_stale": False,
            "change_7d_pct": None,
            "change_30d_pct": None,
        }

    monkeypatch.setattr(ia, "_price_and_changes", fake_price_and_changes)

    summaries = ia.instrument_summaries_for_group("demo")
    by_ticker = {row["ticker"]: row for row in summaries}

    assert by_ticker["AAA.L"]["grouping"] == "Explicit"
    assert by_ticker["BBB.L"]["grouping"] == "Sector B"
    assert by_ticker["CCC.L"]["grouping"] == "Region C"


def test_instrument_summaries_workers_inherit_cache_only(monkeypatch):
    """#9383: the _price_and_changes pool must honour the caller's cache_only()."""
    from backend.timeseries.cache import cache_only, is_cache_only

    holdings = [{"ticker": f"T{i}.L", "name": f"T{i}", "units": 1.0, "market_value_gbp": 1.0} for i in range(12)]
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: {"accounts": [{"holdings": holdings}]})
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})
    seen = []

    def record_price_and_changes(ticker: str) -> dict:
        seen.append(is_cache_only())
        return {"last_price_gbp": None, "change_7d_pct": None, "change_30d_pct": None}

    monkeypatch.setattr(ia, "_price_and_changes", record_price_and_changes)

    with cache_only():
        ia.instrument_summaries_for_group("demo")
    assert seen == [True] * len(holdings)


def test_instrument_summaries_fetches_prices_concurrently(monkeypatch):
    """Regression test: per-ticker price/change fetches must run concurrently,
    not one at a time.

    price_change_pct/_close_on (behind _price_and_changes) are I/O-bound S3
    reads -- confirmed live in production to cost ~1s+ per ticker, making a
    10-ticker group ~6-12s sequential. A sleep-based fake stands in for that
    I/O cost here: if the tickers were still fetched sequentially this test
    would take num_tickers * SLEEP_SECONDS; run concurrently it takes about
    one SLEEP_SECONDS regardless of ticker count.
    """

    tickers = [f"T{i}.L" for i in range(6)]
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": t, "name": t, "units": 1.0, "market_value_gbp": 10.0, "gain_gbp": 1.0} for t in tickers
                ]
            }
        ]
    }
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: portfolio)
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})

    SLEEP_SECONDS = 0.2

    def slow_price_and_changes(ticker: str) -> dict:
        time.sleep(SLEEP_SECONDS)
        return {
            "last_price_gbp": 1.0,
            "last_price_date": "2024-01-01",
            "last_price_time": None,
            "is_stale": False,
            "change_7d_pct": None,
            "change_30d_pct": None,
        }

    monkeypatch.setattr(ia, "_price_and_changes", slow_price_and_changes)

    started = time.monotonic()
    summaries = ia.instrument_summaries_for_group("demo")
    elapsed = time.monotonic() - started

    assert {row["ticker"] for row in summaries} == set(tickers)
    # Sequential would take len(tickers) * SLEEP_SECONDS (1.2s here); allow
    # generous headroom for scheduling/thread-pool overhead in CI while still
    # clearly failing if this regresses to one-ticker-at-a-time.
    assert elapsed < len(tickers) * SLEEP_SECONDS * 0.75


def _flat_price_and_changes(ticker: str) -> dict:
    return {
        "last_price_gbp": 1.0,
        "last_price_date": "2024-01-01",
        "last_price_time": None,
        "is_stale": False,
        "change_7d_pct": None,
        "change_30d_pct": None,
    }


def test_instrument_summaries_exclude_unknown_gain_from_gain_pct(monkeypatch):
    """#8471: a holding with gain_gbp None (unknown cost) must not count its
    market value as cost -- that would dilute the ticker's gain_pct."""
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    # Known lot: cost 100, gain 20 -> 20%.
                    {"ticker": "MIX.L", "name": "Mixed", "units": 1.0, "market_value_gbp": 120.0, "gain_gbp": 20.0},
                    {"ticker": "MIX.L", "name": "Mixed", "units": 1.0, "market_value_gbp": 80.0, "gain_gbp": None},
                    {"ticker": "UNK.L", "name": "Unknown", "units": 1.0, "market_value_gbp": 50.0, "gain_gbp": None},
                ]
            }
        ]
    }
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: portfolio)
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})
    monkeypatch.setattr(ia, "_price_and_changes", _flat_price_and_changes)

    by_ticker = {row["ticker"]: row for row in ia.instrument_summaries_for_group("demo")}

    mixed = by_ticker["MIX.L"]
    assert mixed["market_value_gbp"] == pytest.approx(200.0)
    assert mixed["gain_gbp"] == pytest.approx(20.0)
    assert mixed["gain_pct"] == pytest.approx(20.0)
    unknown = by_ticker["UNK.L"]
    assert unknown["market_value_gbp"] == pytest.approx(50.0)
    assert unknown["gain_pct"] is None
    for row in by_ticker.values():
        assert not [key for key in row if key.startswith("_")]


def test_instrument_summaries_entries_carry_no_private_keys_when_decoration_fails(monkeypatch):
    """The #8471 known-gain accumulator lives outside the response entries, so
    an exception part-way through decoration cannot leave private keys on them."""
    holding = {"ticker": "AAA.L", "name": "Alpha", "units": 1.0, "market_value_gbp": 10.0, "gain_gbp": 1.0}
    portfolio = {"accounts": [{"holdings": [holding]}]}
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug, **_: portfolio)
    monkeypatch.setattr(ia, "get_security_meta", lambda t: {})
    monkeypatch.setattr(ia, "_price_and_changes", _flat_price_and_changes)
    seen: list[dict] = []

    def failing_grouping(meta, entry, current=None):
        seen.append(dict(entry))
        raise RuntimeError("boom")

    monkeypatch.setattr(ia, "_resolve_grouping_details", failing_grouping)

    with pytest.raises(RuntimeError, match="boom"):
        ia.instrument_summaries_for_group("demo")

    assert seen
    assert not [key for key in seen[0] if key.startswith("_")]
