"""Scheduled look-through refresh and the bot run (#10482). No network access."""

from __future__ import annotations

from datetime import date

import pytest
import requests

from backend.fund_upkeep import bot, look_through_upkeep, proposals
from tests.backend.fund_upkeep.test_charges_agent import GOOD_ANSWER, FakeSession, scripted_llm

TODAY = date(2026, 10, 9)


def _fund(ticker, fetched=None, isin="GB00EXAMPLE1"):
    meta = {"isin": isin}
    if fetched:
        meta["look_through"] = {"fetched": fetched}
    return {"ticker": ticker, "isin": isin, "meta": meta}


def test_only_blocks_older_than_max_age_are_refreshed_with_a_pause_between():
    refreshed, pauses = [], []

    def refresh(ticker):
        refreshed.append(ticker)
        return {"updated": ticker != "NOSRC.L"}

    funds = [
        _fund("FRESH.L", fetched="2026-10-01"),
        _fund("STALE.L", fetched="2026-08-01"),
        _fund("NEVER.L"),
        _fund("NOSRC.L"),
        _fund("NOISIN.L", isin=None),
    ]
    out = look_through_upkeep.refresh_stale(funds, today=TODAY, max_age_days=25, refresh=refresh, sleep=pauses.append)

    assert refreshed == ["STALE.L", "NEVER.L", "NOSRC.L"]
    assert pauses == [1.5, 1.5]
    assert [f["ticker"] for f in out["fresh"]] == ["FRESH.L"]
    assert [f["ticker"] for f in out["refreshed"]] == ["STALE.L", "NEVER.L"]
    assert out["unresolved"] == [
        {"ticker": "NOSRC.L", "reason": "no source"},
        {"ticker": "NOISIN.L", "reason": "no ISIN"},
    ]


def test_source_failure_is_reported_and_the_run_continues():
    def refresh(ticker):
        if ticker == "BAD.L":
            raise requests.ConnectionError("down")
        return {"updated": True}

    out = look_through_upkeep.refresh_stale(
        [_fund("BAD.L"), _fund("OK.L")], today=TODAY, refresh=refresh, sleep=lambda _s: None
    )

    assert out["failed"] == [{"ticker": "BAD.L", "reason": "source request failed"}]
    assert out["refreshed"] == [{"ticker": "OK.L"}]


PORTFOLIO = {
    "accounts": [
        {
            "account_type": "ISA",
            "holdings": [{"ticker": "FUNDX.L", "market_value_gbp": 1000.0, "ongoing_charge_pct": None}],
        }
    ]
}

EXPOSURE = {
    "total_value_gbp": 1000.0,
    "holdings": [],
    "countries": [{"label": "Not looked through", "value_gbp": 1000.0, "weight_pct": 100.0}],
    "sectors": [],
    "coverage": {"not_covered_value_gbp": 1000.0},
}


@pytest.fixture(autouse=True)
def stub_exposure(monkeypatch):
    # The real compute_look_through builds portfolio_utils' process-wide
    # securities cache; built against the temporary catalogue it would leak
    # into later tests. Concentration has its own tests (test_concentration.py).
    monkeypatch.setattr(bot, "compute_look_through", lambda _portfolio: EXPOSURE)


def test_run_queues_a_proposal_and_writes_nothing(catalogue):
    before = (catalogue / "L" / "FUNDX.json").read_text(encoding="utf-8")
    toolbox = bot.charges_agent.ReadOnlyToolbox(session=FakeSession(), brave_api_key="k")

    result = bot.run(
        owner="alex",
        portfolio=PORTFOLIO,
        transactions=[],
        today=TODAY,
        llm=scripted_llm(GOOD_ANSWER),
        toolbox=toolbox,
        refresh_kwargs={"refresh": lambda t: {"updated": False}, "sleep": lambda _s: None},
    )

    assert result["ongoing_charges"][0]["status"] == "queued"
    assert result["look_through"]["unresolved"] == [{"ticker": "FUNDX.L", "reason": "no source"}]
    assert result["pending_proposals"] == 1
    assert result["all_in_cost"]["total"]["unknown_value_gbp"] == 1000.0
    # Proposals only: the instrument file is untouched until approval.
    assert (catalogue / "L" / "FUNDX.json").read_text(encoding="utf-8") == before
    assert proposals.list_proposals("pending")[0]["source_url"] == GOOD_ANSWER["source_url"]
    # The run stores a snapshot for the next run's comparison.
    assert bot.previous_snapshot("alex") is not None


def test_offline_run_skips_network_steps(catalogue):
    def must_not_fetch(_ticker):
        raise AssertionError("offline run fetched")

    result = bot.run(
        owner="alex",
        portfolio=PORTFOLIO,
        transactions=[],
        today=TODAY,
        llm=scripted_llm(GOOD_ANSWER),
        fetch=False,
        refresh_kwargs={"refresh": must_not_fetch},
    )

    assert result["look_through"] == {"skipped": "offline"}
    assert result["ongoing_charges"] == {"skipped": "offline", "funds": ["FUNDX.L"]}
    assert proposals.list_proposals() == []


def test_settings_round_trip(catalogue):
    saved = bot.save_settings("Alex", {"single_stock_pct": 7.5, "country_pct": "bad"})

    assert saved["thresholds"]["single_stock_pct"] == 7.5
    assert bot.get_settings("alex") == saved
