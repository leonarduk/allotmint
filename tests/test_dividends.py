"""Tests for automated dividend collection (issue #2750).

The yfinance client is always mocked here — no live network calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.common import dividends
from backend.common.accounts_store import LocalAccountsStore


def _dividends_series(entries: dict[str, float]) -> pd.Series:
    index = pd.to_datetime(list(entries.keys()))
    return pd.Series(list(entries.values()), index=index)


# A recent ex-date, well within the first-run lookback window, so tests don't
# depend on the current date being close to a hardcoded one.
RECENT_EX_DATE = (pd.Timestamp.today() - pd.Timedelta(days=10)).date().isoformat()


def _make_holding(owner: str, account: str, ticker: str, units: float, tmp_path, *, buy_date="2024-01-01"):
    owner_dir = tmp_path / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    (owner_dir / f"{account}.json").write_text(
        json.dumps(
            {
                "owner": owner,
                "account_type": account,
                "currency": "GBP",
                "holdings": [{"ticker": ticker, "units": units}],
            }
        )
    )
    (owner_dir / f"{account}_transactions.json").write_text(
        json.dumps(
            {
                "owner": owner,
                "account_type": account,
                "transactions": [
                    {
                        "type": "BUY",
                        "ticker": ticker,
                        "date": buy_date,
                        "units": units,
                        "price_gbp": 1.0,
                    }
                ],
            }
        )
    )


def _store(tmp_path, monkeypatch) -> LocalAccountsStore:
    store = LocalAccountsStore(root=tmp_path)
    # Rebuilding holdings from transactions is exercised by existing
    # portfolio_loader tests; stub it out here so this module's tests stay
    # focused on dividend fetch/dedup/write behaviour.
    monkeypatch.setattr(store, "rebuild_portfolio", lambda owner, account: None)
    monkeypatch.setattr(dividends, "_resolve_store", lambda: store)
    return store


def _read_transactions(tmp_path, owner, account) -> list[dict]:
    data = json.loads((tmp_path / owner / f"{account}_transactions.json").read_text())
    return data["transactions"]


def test_refresh_dividends_creates_new_dividend_transaction(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "AAA.L", 100, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: 0.5})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 1
    assert summary["skipped_tickers"] == []

    txs = _read_transactions(tmp_path, "alice", "isa")
    new_divs = [t for t in txs if t["type"] == "DIVIDEND"]
    assert len(new_divs) == 1
    assert new_divs[0]["ticker"] == "AAA.L"
    assert new_divs[0]["date"] == RECENT_EX_DATE
    # 0.5/share * 100 units = 50.00 GBP -> 5000 pence
    assert new_divs[0]["amount_minor"] == 5000
    assert new_divs[0]["currency"] == "GBP"


def test_refresh_dividends_is_idempotent_on_rerun(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "AAA.L", 100, tmp_path)
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: 0.5})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    first = dividends.refresh_dividends()
    second = dividends.refresh_dividends()

    assert first["dividends_created"] == 1
    assert second["dividends_created"] == 0

    txs = _read_transactions(tmp_path, "alice", "isa")
    new_divs = [t for t in txs if t["type"] == "DIVIDEND"]
    assert len(new_divs) == 1, "re-running must not duplicate the dividend transaction"


def test_refresh_dividends_skips_unrecognised_ticker(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "OEIC1", 10, tmp_path)
    _store(tmp_path, monkeypatch)

    def _raise(ticker):
        raise ValueError(f"{ticker}: no data found")

    monkeypatch.setattr(dividends.yf, "Ticker", lambda ticker: SimpleNamespace(dividends=_raise(ticker)))
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert summary["skipped_tickers"] == ["OEIC1"]
    txs = _read_transactions(tmp_path, "alice", "isa")
    assert not any(t["type"] == "DIVIDEND" for t in txs)


def test_refresh_dividends_empty_series_is_skipped_not_errored(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "OEIC2", 10, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(dividends.yf, "Ticker", lambda ticker: SimpleNamespace(dividends=pd.Series(dtype=float)))
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert summary["skipped_tickers"] == ["OEIC2"]


def test_refresh_dividends_ignores_declarations_older_than_lookback_on_first_run(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "AAA.L", 100, tmp_path, buy_date="2000-01-01")
    _store(tmp_path, monkeypatch)

    old_date = (pd.Timestamp.today() - pd.Timedelta(days=365)).date().isoformat()
    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({old_date: 0.5})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0


def test_refresh_dividends_converts_pence_currency(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "BBB.L", 10, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: 5.0})),
    )
    # GBp (pence) instrument: 5.0 pence/share -> 0.05 GBP/share
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBp"})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 1
    txs = _read_transactions(tmp_path, "alice", "isa")
    new_div = next(t for t in txs if t["type"] == "DIVIDEND")
    # 5.0 pence/share * 10 units = 50 pence = 0.50 GBP -> 50 minor units
    assert new_div["amount_minor"] == 50


def test_refresh_dividends_skips_zero_unit_holding(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "AAA.L", 0, tmp_path)
    _store(tmp_path, monkeypatch)

    called = []
    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: called.append(ticker) or SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: 0.5})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert not called, "provider must not be queried for a zero-unit holding"


def test_refresh_dividends_processes_multiple_owners_and_accounts(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "AAA.L", 100, tmp_path)
    _make_holding("bob", "sipp", "AAA.L", 50, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: 0.5})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert summary["accounts_processed"] == 2
    assert summary["dividends_created"] == 2
    alice_div = next(t for t in _read_transactions(tmp_path, "alice", "isa") if t["type"] == "DIVIDEND")
    bob_div = next(t for t in _read_transactions(tmp_path, "bob", "sipp") if t["type"] == "DIVIDEND")
    assert alice_div["amount_minor"] == 5000
    assert bob_div["amount_minor"] == 2500


def test_refresh_dividends_no_live_network_import(monkeypatch):
    """Guard against accidentally calling the real yfinance client in CI."""
    called = []
    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: called.append(ticker) or pytest.fail("must not construct a real yfinance Ticker in tests"),
    )
    # No holdings configured -> refresh_dividends() must not touch the provider at all.
    store = LocalAccountsStore(root=None)
    monkeypatch.setattr(dividends, "_resolve_store", lambda: store)

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert not called
