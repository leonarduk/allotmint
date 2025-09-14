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
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, l: None)
    ia._price_and_changes.cache_clear()
    res = ia._price_and_changes("FOO")
    assert res["last_price_gbp"] is None
    assert res["is_stale"] is True


def test_price_and_changes_snapshot(monkeypatch):
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, l: ("ABC", "L"))
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
    monkeypatch.setattr(ia, "_resolve_full_ticker", lambda t, l: ("ABC", "L"))
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
    monkeypatch.setattr(ia, "build_group_portfolio", lambda slug: gp)
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
