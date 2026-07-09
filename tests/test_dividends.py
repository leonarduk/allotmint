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


class _RaisingDividends:
    """Simulates yfinance raising when ``.dividends`` is *accessed* (a network
    call), as opposed to when ``Ticker(...)`` is merely constructed — the
    real-world failure point for an unrecognised/delisted ticker."""

    def __init__(self, ticker: str):
        self._ticker = ticker

    @property
    def dividends(self):
        raise ValueError(f"{self._ticker}: no data found")


def test_refresh_dividends_skips_unrecognised_ticker(tmp_path, monkeypatch):
    _make_holding("alice", "isa", "OEIC1", 10, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(dividends.yf, "Ticker", _RaisingDividends)
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert summary["skipped_tickers"] == ["OEIC1"]
    txs = _read_transactions(tmp_path, "alice", "isa")
    assert not any(t["type"] == "DIVIDEND" for t in txs)


def test_refresh_dividends_empty_series_is_not_treated_as_skip(tmp_path, monkeypatch):
    """A recognised ticker that simply pays no dividends (e.g. a growth stock)
    must not be reported as skipped/unrecognised — yfinance returns an empty
    series for both cases, so only an actual provider exception counts as a
    skip. See regression note in _fetch_new_dividends."""
    _make_holding("alice", "isa", "GOOGL", 10, tmp_path)
    _store(tmp_path, monkeypatch)

    monkeypatch.setattr(dividends.yf, "Ticker", lambda ticker: SimpleNamespace(dividends=pd.Series(dtype=float)))
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 0
    assert summary["skipped_tickers"] == []
    assert summary["tickers_processed"] == 1


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


def test_refresh_dividends_handles_multiple_tickers_in_one_account(tmp_path, monkeypatch):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir(parents=True)
    (owner_dir / "isa.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "isa",
                "currency": "GBP",
                "holdings": [
                    {"ticker": "AAA.L", "units": 100},
                    {"ticker": "BBB.L", "units": 20},
                ],
            }
        )
    )
    (owner_dir / "isa_transactions.json").write_text(
        json.dumps(
            {
                "owner": "alice",
                "account_type": "isa",
                "transactions": [
                    {"type": "BUY", "ticker": "AAA.L", "date": "2024-01-01", "units": 100, "price_gbp": 1.0},
                    {"type": "BUY", "ticker": "BBB.L", "date": "2024-01-01", "units": 20, "price_gbp": 1.0},
                ],
            }
        )
    )
    _store(tmp_path, monkeypatch)

    per_share = {"AAA.L": 0.5, "BBB.L": 0.3}
    monkeypatch.setattr(
        dividends.yf,
        "Ticker",
        lambda ticker: SimpleNamespace(dividends=_dividends_series({RECENT_EX_DATE: per_share[ticker]})),
    )
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert summary["dividends_created"] == 2
    txs = _read_transactions(tmp_path, "alice", "isa")
    new_divs = {t["ticker"]: t for t in txs if t["type"] == "DIVIDEND"}
    assert set(new_divs) == {"AAA.L", "BBB.L"}
    assert new_divs["AAA.L"]["amount_minor"] == 5000  # 0.5 * 100 units
    assert new_divs["BBB.L"]["amount_minor"] == 600  # 0.3 * 20 units


def test_refresh_dividends_dedupes_multiple_declarations_same_ex_date(tmp_path, monkeypatch):
    """If the provider ever returns two entries for the same (ticker, ex_date)
    pair, only one DIVIDEND transaction should be written per key."""
    _make_holding("alice", "isa", "AAA.L", 100, tmp_path)
    _store(tmp_path, monkeypatch)

    call_count = []

    def _fake_fetch(ticker, *, since):
        call_count.append(ticker)
        # Simulate a regular + special dividend landing on the same ex-date.
        return [
            {"ex_date": RECENT_EX_DATE, "amount_per_share": 0.5},
            {"ex_date": RECENT_EX_DATE, "amount_per_share": 0.5},
        ]

    monkeypatch.setattr(dividends, "_fetch_new_dividends", _fake_fetch)
    monkeypatch.setattr(dividends, "get_instrument_meta", lambda ticker: {"currency": "GBP"})

    summary = dividends.refresh_dividends()

    assert call_count == ["AAA.L"]
    assert summary["dividends_created"] == 1, "only the first declaration for a given (ticker, ex_date) is kept"
    txs = _read_transactions(tmp_path, "alice", "isa")
    assert len([t for t in txs if t["type"] == "DIVIDEND"]) == 1


def test_fetch_new_dividends_filters_and_shapes_declarations():
    """Direct unit test of _fetch_new_dividends: filters non-positive amounts
    and dates on/before the cutoff, and shapes the remaining entries."""
    old_date = (pd.Timestamp.today() - pd.Timedelta(days=365)).date().isoformat()
    zero_amount_date = (pd.Timestamp.today() - pd.Timedelta(days=1)).date().isoformat()
    series = _dividends_series(
        {
            old_date: 0.5,  # excluded: older than the default lookback cutoff
            zero_amount_date: 0.0,  # excluded: non-positive amount
            RECENT_EX_DATE: 0.4,  # included
        }
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dividends.yf, "Ticker", lambda ticker: SimpleNamespace(dividends=series))
        result = dividends._fetch_new_dividends("AAA.L", since=None)

    assert result is not None
    dates = {d["ex_date"] for d in result}
    assert RECENT_EX_DATE in dates
    assert old_date not in dates, "declarations at/before the lookback cutoff must be excluded"
    assert all(d["amount_per_share"] > 0 for d in result), "non-positive amounts must be filtered out"


def test_fetch_new_dividends_returns_none_on_provider_exception():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dividends.yf, "Ticker", _RaisingDividends)
        result = dividends._fetch_new_dividends("BAD.L", since=None)

    assert result is None


def test_fetch_new_dividends_returns_empty_list_for_empty_series():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dividends.yf, "Ticker", lambda ticker: SimpleNamespace(dividends=pd.Series(dtype=float)))
        result = dividends._fetch_new_dividends("GOOGL", since=None)

    assert result == []
