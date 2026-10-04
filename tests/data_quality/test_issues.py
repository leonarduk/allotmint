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
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)

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


def test_aggregate_holding_issues_missing_series_unresolvable(monkeypatch, tmp_path, accounts_root):
    """Metadata exists but the symbol can't be resolved: MISSING_SERIES uses the
    holding's own ticker instead of raising (regression for #6727)."""
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: False)

    issues = aggregate_holding_issues(accounts_root)
    missing = [i for i in issues if i.type == IssueType.MISSING_SERIES]
    assert {i.fix_payload["ticker"] for i in missing} == {"VWRL", "MICC", "PFE"}


def test_cash_holdings_skipped(monkeypatch, tmp_path, accounts_root):
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)

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


@pytest.fixture(autouse=True)
def _empty_refresh_universe(monkeypatch):
    """Keep series tests off the real portfolios/triggers (#8599)."""
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: [])


def _patch_stale_cache(monkeypatch, pairs):
    df = pd.DataFrame(
        {"Date": ["2000-01-03", "2000-01-04"], "Close": [100.0, 101.0]},
    )
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: list(pairs))
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: df.copy())
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})


def _stale_types(issues):
    return {
        f"{i.entity['ticker']}.{i.entity['exchange']}": i.type
        for i in issues
        if i.type in (IssueType.STALE_SERIES, IssueType.UNTRACKED_STALE_SERIES)
    }


def test_aggregate_series_issues_stale(monkeypatch):
    """A stale series the refresh covers is STALE_SERIES with a refetch fix."""
    _patch_stale_cache(monkeypatch, [("ABC", "L")])
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: ["ABC.L"])

    issues = aggregate_series_issues(stale_max_age_days=5)

    stale = [i for i in issues if i.type == IssueType.STALE_SERIES]
    assert len(stale) == 1
    assert stale[0].severity == "medium"
    assert stale[0].fixable is True
    assert stale[0].fix_payload == {"kind": "refetch", "ticker": "ABC", "exchange": "L"}


def test_aggregate_series_issues_untracked_stale_is_separate(monkeypatch):
    """A stale series nobody holds or watches is an orphan, not a refresh failure (#8599)."""
    _patch_stale_cache(monkeypatch, [("SKG", "L")])

    issues = aggregate_series_issues(stale_max_age_days=5)

    assert _stale_types(issues) == {"SKG.L": IssueType.UNTRACKED_STALE_SERIES}
    orphan = next(i for i in issues if i.type == IssueType.UNTRACKED_STALE_SERIES)
    assert orphan.id == "UNTRACKED_STALE_SERIES:SKG:L"
    assert orphan.severity == "low"
    assert orphan.fixable is False
    assert "not held or watched" in orphan.description


def test_aggregate_series_issues_classifies_against_holdings_and_watchlist(monkeypatch, tmp_path):
    """Held (from accounts_root), watched, bare-suffix and orphan series are split correctly."""
    _patch_stale_cache(monkeypatch, [("VOD", "L"), ("WAT", "N"), ("AV", "L"), ("PBR", "N"), ("JPM", "N")])
    owner = tmp_path / "demo"
    owner.mkdir()
    holdings = [{"ticker": "VOD.L"}, {"ticker": "AV."}, {"ticker": "PBR-A.N"}]
    (owner / "isa.json").write_text(json.dumps({"owner": "demo", "holdings": holdings}), encoding="utf-8")
    monkeypatch.setattr(issues_module, "_refresh_universe", lambda: ["WAT.N"])

    issues = aggregate_series_issues(stale_max_age_days=5, accounts_root=tmp_path)

    assert _stale_types(issues) == {
        "VOD.L": IssueType.STALE_SERIES,
        "WAT.N": IssueType.STALE_SERIES,
        # A bare holding ticker matches on symbol so a suffix bug never hides a held series.
        "AV.L": IssueType.STALE_SERIES,
        # Same symbol root on a different line is still an orphan.
        "PBR.N": IssueType.UNTRACKED_STALE_SERIES,
        "JPM.N": IssueType.UNTRACKED_STALE_SERIES,
    }


def test_aggregate_series_issues_unknown_universe_reports_all_as_stale(monkeypatch, caplog):
    """If the refresh universe can't be loaded, never under-report: everything stays STALE_SERIES."""
    _patch_stale_cache(monkeypatch, [("SKG", "L")])

    def _boom():
        raise RuntimeError("portfolios unavailable")

    monkeypatch.setattr(issues_module, "_refresh_universe", _boom)

    with caplog.at_level("WARNING", logger=issues_module.__name__):
        issues = aggregate_series_issues(stale_max_age_days=5)

    assert _stale_types(issues) == {"SKG.L": IssueType.STALE_SERIES}
    assert "refresh universe" in caplog.text


def test_aggregate_issues_threads_accounts_root_to_series(monkeypatch, tmp_path):
    """aggregate_issues classifies stale series against the request's accounts_root."""
    _patch_stale_cache(monkeypatch, [("VOD", "L")])
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: True)
    monkeypatch.setattr(issues_module, "_implausible_book_cost_issue", lambda *a, **k: None)
    owner = tmp_path / "demo"
    owner.mkdir()
    (owner / "isa.json").write_text(
        json.dumps({"owner": "demo", "holdings": [{"ticker": "VOD.L"}]}),
        encoding="utf-8",
    )

    issues = aggregate_issues(tmp_path, stale_max_age_days=5)

    assert _stale_types(issues) == {"VOD.L": IssueType.STALE_SERIES}


def test_aggregate_issues_dedupes_across_sources(monkeypatch, tmp_path, accounts_root):
    """aggregate_issues returns one issue per (type, entity) pair."""
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {})
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)
    monkeypatch.setattr(issues_module, "list_cached_meta_tickers", lambda: [])
    monkeypatch.setattr(issues_module, "load_cached_meta_timeseries_full", lambda t, e: None)

    issues = aggregate_issues(accounts_root)
    ids = [i.id for i in issues]
    assert len(ids) == len(set(ids))


def _write_booked_holdings(tmp_path, holdings):
    owner = tmp_path / "demo"
    owner.mkdir(exist_ok=True)
    doc = {"owner": "demo", "account_type": "isa", "currency": "GBP", "holdings": holdings}
    (owner / "isa.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def _patch_book_cost_env(monkeypatch, current_price):
    """Metadata present and series cached so only the book-cost check fires."""
    from backend.common import holding_utils, instrument_api
    from backend.common import portfolio_utils as pu

    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "x"})
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: f"{symbol}.L")
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: True)
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda full, cache: (full.split(".")[0], "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {})
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: None)
    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", lambda *a, **k: (current_price, "mock"))
    monkeypatch.setattr(
        holding_utils,
        "_get_dated_price_for_date_scaled",
        lambda ticker, exchange, d, *a, **k: (current_price, "mock", d if current_price is not None else None),
    )
    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", lambda *a, **k: None)


def test_aggregate_holding_issues_flags_implausible_book_cost(monkeypatch, tmp_path):
    """#8472: a booked cost implying ~1/100 of the price is surfaced as an
    IMPLAUSIBLE_BOOK_COST issue; a plausible one is not."""
    root = _write_booked_holdings(
        tmp_path,
        [
            {"ticker": "AV.L", "units": 50, "cost_basis_gbp": 263},
            {"ticker": "OK.L", "units": 50, "cost_basis_gbp": 30000},
            {"ticker": "NOCOST.L", "units": 50},
        ],
    )
    _patch_book_cost_env(monkeypatch, current_price=672.40)

    issues = aggregate_holding_issues(root)

    flagged = [i for i in issues if i.type == IssueType.IMPLAUSIBLE_BOOK_COST]
    assert [i.entity for i in flagged] == [{"owner": "demo", "account": "isa", "holding": "AV.L"}]
    issue = flagged[0]
    assert issue.id == "IMPLAUSIBLE_BOOK_COST:demo:isa:AV.L"
    assert issue.severity == "high"
    assert issue.fixable is False
    assert issue.preview["before"] == {"cost_basis_gbp": 263, "warning": "implied_unit_cost_out_of_band"}
    assert "AV.L" in issue.description


def test_aggregate_holding_issues_book_check_does_not_mutate_holdings_file(monkeypatch, tmp_path):
    root = _write_booked_holdings(tmp_path, [{"ticker": "AV.L", "units": 50, "cost_basis_gbp": 263}])
    before = (root / "demo" / "isa.json").read_text(encoding="utf-8")
    _patch_book_cost_env(monkeypatch, current_price=672.40)

    aggregate_holding_issues(root)

    assert (root / "demo" / "isa.json").read_text(encoding="utf-8") == before


def test_aggregate_holding_issues_flags_missing_asset_class(monkeypatch, tmp_path, accounts_root):
    """A held instrument without a recognised asset class is MISSING_ASSET_CLASS (#9196)."""
    metas = {
        "VWRL.L": {"name": "Vanguard FTSE All-World", "asset_class": "equity"},
        "MICC.L": {"name": "Magnum", "asset_class": "Fund"},
        "PFE.N": {"name": "Pfizer"},
    }
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: metas.get(t, {}))
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: True)

    issues = aggregate_holding_issues(accounts_root)
    missing = {i.id: i for i in issues if i.type == IssueType.MISSING_ASSET_CLASS}

    assert set(missing) == {"MISSING_ASSET_CLASS:MICC:L", "MISSING_ASSET_CLASS:PFE:N"}
    issue = missing["MISSING_ASSET_CLASS:PFE:N"]
    assert issue.entity == {"ticker": "PFE", "exchange": "N"}
    assert issue.severity == "low"
    assert issue.fixable is False


def test_missing_asset_class_reported_once_per_instrument(monkeypatch, tmp_path):
    """The same unclassified instrument held in two accounts yields one issue."""
    owner = tmp_path / "demo"
    owner.mkdir()
    for account in ("isa", "sipp"):
        document = {"owner": "demo", "account_type": account, "holdings": [{"ticker": "PFE.N"}]}
        (owner / f"{account}.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(issues_module, "get_instrument_meta", lambda t: {"name": "Pfizer"})
    monkeypatch.setattr(issues_module, "resolve_instrument_ticker", lambda symbol, create_missing=False: None)
    monkeypatch.setattr(issues_module, "has_cached_meta_timeseries", lambda t, e: True)

    issues = aggregate_holding_issues(tmp_path)

    assert [i.id for i in issues if i.type == IssueType.MISSING_ASSET_CLASS] == ["MISSING_ASSET_CLASS:PFE:N"]
