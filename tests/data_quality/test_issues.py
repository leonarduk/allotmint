"""Unit tests for backend/data_quality/issues.py aggregation (no live fetches)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from backend.data_quality import issues as issues_module
from backend.data_quality.issues import (
    IssueType,
    aggregate_holding_issues,
    aggregate_issues,
    aggregate_series_issues,
)


@pytest.fixture
def accounts_root(tmp_path):
    owner = tmp_path / "demo"
    owner.mkdir()
    (owner / "person.json").write_text(
        json.dumps({"owner": "demo", "holdings": []}),
        encoding="utf-8",
    )
    isa = {
        "owner": "demo",
        "account_type": "isa",
        "currency": "GBP",
        "holdings": [
            {"ticker": "VWRL.L"},
            {"ticker": "MICC.L"},  # wrong exchange: resolves to MICC.N
            {"ticker": "PFE.N"},
            {"ticker": "CASH.GBP"},
        ],
    }
    (owner / "isa.json").write_text(json.dumps(isa), encoding="utf-8")
    return tmp_path


def _write_instrument_meta(tmp_path, symbol, exchange, name="Test Instrument"):
    path = tmp_path / "instruments" / exchange / f"{symbol}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ticker": f"{symbol}.{exchange}", "exchange": exchange, "name": name}),
        encoding="utf-8",
    )


def test_aggregate_holding_issues_wrong_exchange(monkeypatch, tmp_path, accounts_root):
    """A holding whose exchange has no metadata but resolves elsewhere is WRONG_EXCHANGE."""
    _write_instrument_meta(tmp_path, "MICC", "N", name="MercadoLibre")

    def fake_meta(ticker: str) -> dict:
        return {"name": "MercadoLibre", "ticker": ticker} if ticker == "MICC.N" else {}

    def fake_resolve(symbol, create_missing=False):
        return "MICC.N" if symbol == "MICC" else None

    monkeypatch.setattr(issues_module, "get_instrument_meta", fake_meta)
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", fake_resolve)
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: True)

    issues = aggregate_holding_issues(accounts_root)
    wrong = [i for i in issues if i.type == IssueType.WRONG_EXCHANGE]
    assert len(wrong) == 1
    assert wrong[0].entity["holding"] == "MICC.L"
    assert wrong[0].suggested_fix == "Correct holding exchange to MICC.N."


def test_aggregate_holding_issues_unresolved(monkeypatch, tmp_path, accounts_root):
    """A holding with no metadata and no resolution is UNRESOLVED_TICKER."""
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})
    monkeypatch.setattr(
        issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None
    )

    issues = aggregate_holding_issues(accounts_root)
    unresolved = [i for i in issues if i.type == IssueType.UNRESOLVED_TICKER]
    # MICC.L and VWRL.L and PFE.N all have no metadata and don't resolve.
    assert len(unresolved) == 3


def test_aggregate_holding_issues_missing_series(monkeypatch, tmp_path, accounts_root):
    """A holding with metadata but no cached series is MISSING_SERIES."""
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})
    monkeypatch.setattr(
        issues_module,
        "resolve_instrument_ticker",
        lambda symbol, create_missing=False: f"{symbol}.L",
    )
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: False)

    issues = aggregate_holding_issues(accounts_root)
    missing = [i for i in issues if i.type == IssueType.MISSING_SERIES]
    assert len(missing) == 3  # VWRL.L, MICC.L -> MICC.L, PFE.N -> PFE.L


def test_cash_holdings_skipped(monkeypatch, tmp_path, accounts_root):
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})
    monkeypatch.setattr(
        issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None
    )

    issues = aggregate_holding_issues(accounts_root)
    assert all("CASH" not in i.entity.get("holding", "") for i in issues)


def test_aggregate_series_issues_detects_gaps_duplicates_outliers(monkeypatch):
    dates = [f"2026-01-{d:02d}" for d in range(3, 25)]
    closes = [100.0 + i for i in range(len(dates))]
    closes[10] = 500.0  # clear outlier spike
    df = pd.DataFrame(
        {
            "Date": dates,
            "Close": closes,
            "Ticker": ["ABC"] * len(dates),
            "Source": ["Test"] * len(dates),
        }
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})

    issues = aggregate_series_issues(rolling_window=20, outlier_sigma=3.0)
    types = {i.type for i in issues}
    assert IssueType.OUTLIERS in types


def test_aggregate_series_issues_detects_duplicates(monkeypatch):
    df = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "Close": [100.0, 101.0, 102.0],
        },
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})

    issues = aggregate_series_issues()
    dup = [i for i in issues if i.type == IssueType.DUPLICATES]
    assert len(dup) == 1
    assert dup[0].preview["before"]["duplicate_dates"] == ["2026-01-01"]


def test_aggregate_series_issues_missing_metadata(monkeypatch):
    df = pd.DataFrame(
        {"Date": ["2026-01-01", "2026-01-02"], "Close": [100.0, 101.0]},
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})

    issues = aggregate_series_issues()
    assert any(i.type == IssueType.MISSING_METADATA for i in issues)


def test_aggregate_series_issues_ticker_mismatch(monkeypatch):
    df = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-02"],
            "Close": [100.0, 101.0],
            "Ticker": ["WRONG", "WRONG"],
        },
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})

    issues = aggregate_series_issues()
    mismatch = [i for i in issues if i.type == IssueType.TICKER_MISMATCH]
    assert len(mismatch) == 1
    assert mismatch[0].entity == {"ticker": "ABC", "exchange": "L"}


def test_aggregate_series_issues_stale(monkeypatch):
    """A series whose last date is older than the threshold is STALE_SERIES."""
    df = pd.DataFrame(
        {"Date": ["2000-01-03", "2000-01-04"], "Close": [100.0, 101.0]},
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [("ABC", "L")])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})

    issues = aggregate_series_issues(stale_max_age_days=5)
    assert any(i.type == IssueType.STALE_SERIES for i in issues)


def test_aggregate_issues_dedupes_across_sources(monkeypatch, tmp_path, accounts_root):
    """aggregate_issues returns one issue per (type, entity) pair."""
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})
    monkeypatch.setattr(
        issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: None)

    issues = aggregate_issues(accounts_root)
    ids = [i.id for i in issues]
    assert len(ids) == len(set(ids))
