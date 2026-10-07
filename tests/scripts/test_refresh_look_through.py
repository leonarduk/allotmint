"""Tests for scripts/refresh_look_through.py (#9974). No network access."""

from __future__ import annotations

import json

import pytest

from scripts import refresh_look_through as script

BLOCK = {
    "source": "morningstar",
    "as_of": "2026-08-31",
    "fetched": "2026-10-07",
    "countries": {"United States": 60.0, "Japan": 40.0},
    "sectors": {"Information Technology": 100.0},
    "top_holdings": [],
}


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def instruments(tmp_path):
    root = tmp_path / "instruments"
    _write(
        root / "L" / "VWRL.json",
        {"ticker": "VWRL.L", "name": "All-World ETF", "instrumentType": "ETF", "isin": "IE00B3RBWM25"},
    )
    _write(
        root / "L" / "GSK.json",
        {"ticker": "GSK.L", "name": "GSK plc", "instrumentType": "Equity", "isin": "GB00BN7SWP63"},
    )
    _write(root / "L" / "NOISIN.json", {"ticker": "NOISIN.L", "name": "Some ETF", "instrumentType": "ETF"})
    _write(
        root / "L" / "PHAU.json",
        {
            "ticker": "PHAU.L",
            "name": "Physical Gold",
            "instrumentType": "ETC",
            "asset_class": "commodity",
            "isin": "JE00B1VS3770",
        },
    )
    _write(root / "Cash" / "GBP.json", {"name": "Cash", "isin": "XX"})
    return root


@pytest.fixture
def fetched(monkeypatch):
    calls = []

    def _fetch(isin, session, today):
        calls.append(isin)
        return dict(BLOCK) if isin == "IE00B3RBWM25" else None

    monkeypatch.setattr(script, "fetch_look_through", _fetch)
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)
    return calls


def test_only_non_commodity_funds_with_isin_are_candidates(instruments):
    tickers = [meta["ticker"] for _, meta in script.candidate_funds(instruments)]
    assert tickers == ["VWRL.L"]


def test_explicit_ticker_overrides_the_fund_filter(instruments):
    tickers = [meta["ticker"] for _, meta in script.candidate_funds(instruments, {"GSK.L"})]
    assert tickers == ["GSK.L"]


def test_dry_run_does_not_write(instruments, fetched):
    before = (instruments / "L" / "VWRL.json").read_text(encoding="utf-8")
    assert script.main(["--instruments-dir", str(instruments)]) == 0
    assert fetched == ["IE00B3RBWM25"]
    assert (instruments / "L" / "VWRL.json").read_text(encoding="utf-8") == before


def test_write_adds_block_keeping_key_order(instruments, fetched):
    assert script.main(["--instruments-dir", str(instruments), "--write"]) == 0
    meta = json.loads((instruments / "L" / "VWRL.json").read_text(encoding="utf-8"))
    assert list(meta) == ["ticker", "name", "instrumentType", "isin", "look_through"]
    assert meta["look_through"]["countries"] == BLOCK["countries"]


def test_recently_fetched_fund_is_skipped_unless_forced(instruments, fetched):
    path = instruments / "L" / "VWRL.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["look_through"] = {**BLOCK, "fetched": script.date.today().isoformat()}
    _write(path, meta)

    assert script.main(["--instruments-dir", str(instruments)]) == 0
    assert fetched == []
    assert script.main(["--instruments-dir", str(instruments), "--force"]) == 0
    assert fetched == ["IE00B3RBWM25"]


def test_fetch_failure_is_reported_in_exit_code(instruments, monkeypatch):
    def _boom(isin, session, today):
        raise script.LookThroughFetchError("HTTP 403")

    monkeypatch.setattr(script, "fetch_look_through", _boom)
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)
    assert script.main(["--instruments-dir", str(instruments)]) == 1
