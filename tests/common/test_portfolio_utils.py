import pandas as pd
import pytest
from datetime import datetime, timezone

from backend.common import portfolio_utils as pu


def test_compute_var_valid_series():
    df = pd.DataFrame({"Close": [100, 110, 105, 95, 98]})
    var = pu.compute_var(df)
    assert var == pytest.approx(8.6015, rel=1e-3)


def test_compute_var_short_series_returns_none():
    df = pd.DataFrame({"Close": [100]})
    assert pu.compute_var(df) is None


def test_compute_var_invalid_input_raises():
    with pytest.raises(AttributeError):
        pu.compute_var(123)  # type: ignore[arg-type]


def test_fx_to_base_same_currency(monkeypatch):
    called = {"count": 0}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        called["count"] += 1
        return pd.DataFrame({"Rate": [1.0]})

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    rate = pu._fx_to_base("USD", "USD", {})
    assert rate == 1.0
    assert called["count"] == 0


def test_fx_to_base_foreign_currency(monkeypatch):
    df = pd.DataFrame({"Rate": [1.25]})
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *a, **k: df)
    cache: dict[str, float] = {}
    rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.25
    assert cache["USD"] == 1.25


def test_list_all_unique_tickers(monkeypatch):
    sample_portfolios = [
        {
            "owner": "alice",
            "accounts": [
                {"account_type": "isa", "holdings": [{"ticker": "AAA"}, {"ticker": "bbb"}]},
                {"account_type": "sipp", "holdings": [{"ticker": None}]},
            ],
        },
        {
            "owner": "bob",
            "accounts": [
                {"account_type": "taxable", "holdings": [{"ticker": "CCC"}]},
            ],
        },
    ]
    monkeypatch.setattr(pu, "list_portfolios", lambda: sample_portfolios)
    monkeypatch.setattr(pu, "list_virtual_portfolios", lambda: [])
    tickers = pu.list_all_unique_tickers()
    assert tickers == ["AAA", "BBB", "CCC"]


def test_refresh_snapshot_in_memory(monkeypatch):
    snapshot = {"AAA": {"price": 1}}
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT_TS", None)
    pu.refresh_snapshot_in_memory(snapshot, ts)
    assert pu._PRICE_SNAPSHOT == snapshot
    assert pu._PRICE_SNAPSHOT_TS == ts
