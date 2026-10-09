"""A whole trend-watch run for one owner, with mocked prices, data checks and model (#10476)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from backend.agent import trading_agent
from backend.config import TrendWatchConfig
from backend.trend_watch import prompt, storage
from backend.trend_watch.service import alert_text, holdings_by_ticker, run_for_owner

from .fixtures import FRESH_TURN_END, INDEX, double_top, pence_cliff, rising_benchmark

END = FRESH_TURN_END
TURN = double_top().iloc[:END]
PRICES = {
    "TURN.L": TURN,
    "BETA.L": TURN.copy(),
    "BETAIDX.L": TURN.copy(),
    "JEGI.L": pence_cliff(),
    "NOISY.L": TURN.copy(),
    "UP.L": pd.Series(np.linspace(100, 200, END), index=INDEX[:END]),
    "FTAL.L": rising_benchmark().iloc[:END],
}
META = {"BETA.L": {"benchmark": "BETAIDX.L"}}


def _holding(ticker, account, value, cost):
    return {"ticker": ticker, "name": ticker, "market_value_gbp": value, "cost_basis_gbp": cost}


PORTFOLIO = {
    "owner": "alex",
    "total_value_estimate_gbp": 100000.0,
    "accounts": [
        {
            "account_type": "ISA",
            "holdings": [
                {"ticker": "CASH.GBP", "instrument_type": "Cash", "market_value_gbp": 50000.0},
                _holding("TURN.L", "ISA", 10000.0, 12000.0),
                _holding("BETA.L", "ISA", 5000.0, 4000.0),
                _holding("JEGI.L", "ISA", 3000.0, 3000.0),
                _holding("UP.L", "ISA", 2000.0, 1000.0),
            ],
        },
        {
            "account_type": "Brokerage",
            "holdings": [_holding("TURN.L", "GIA", 5000.0, 4000.0), _holding("NOISY.L", "GIA", 1000.0, 900.0)],
        },
    ],
}
NOISY_ISSUE = {
    "id": "ZERO_VOLUME_SPIKE:NOISY:L",
    "type": "ZERO_VOLUME_SPIKE",
    "severity": "medium",
    "entity": {"ticker": "NOISY", "exchange": "L"},
    "description": "Zero-volume price spike on 2025-03-10.",
}


async def _runner(message, policy):
    if '"ticker": "TURN.L"' in message:
        policy.record("search_web", {"query": "TURN plc"}, "TURN plc issues profit warning", False)
        return json.dumps(
            {
                "verdict": "idiosyncratic_deterioration",
                "summary": "A profit warning on 2 March.",
                "evidence": [{"tool": "search_web", "finding": "Profit warning", "value": "-30%", "source": "rns"}],
            }
        )
    return json.dumps({"verdict": "market_wide_move", "summary": "Fell with its index.", "evidence": []})


async def _run(**kwargs):
    return await run_for_owner(
        "alex",
        today=date(2025, 3, 7),
        cfg=kwargs.pop("cfg", TrendWatchConfig()),
        runner=_runner,
        load_portfolio=lambda owner: PORTFOLIO,
        load_prices=lambda ticker, days: PRICES.get(ticker, pd.Series(dtype=float)),
        load_levels=lambda closes, ticker: (closes, "total"),
        load_meta=lambda ticker: META.get(ticker, {}),
        load_issues=kwargs.pop("load_issues", lambda: ([NOISY_ISSUE], [])),
        **kwargs,
    )


async def test_run_sorts_verdicts_and_sends_data_problems_to_check_first():
    report = await _run()

    verdicts = {item["ticker"]: item["verdict"] for item in report["items"]}
    assert verdicts == {
        "TURN.L": prompt.VERDICT_IDIOSYNCRATIC,
        "BETA.L": prompt.VERDICT_MARKET,
        "JEGI.L": prompt.VERDICT_DATA,
        "NOISY.L": prompt.VERDICT_DATA,
    }
    assert [item["ticker"] for item in report["items"]][:2] == ["TURN.L", "BETA.L"]
    assert [item["rank"] for item in report["items"]] == [1, 2, 3, 4]
    jegi = next(item for item in report["items"] if item["ticker"] == "JEGI.L")
    assert jegi["data_issues"][0]["type"] == "PRICE_SCALE_SUSPECT"
    assert jegi["investigation"]["tool_calls"] == []
    assert report["holdings_checked"] == 5
    assert report["not_flagged"] == 1
    assert report["disclaimer"] == prompt.DISCLAIMER
    assert report["backtest"]["horizons"]["1m"]["weeks"] > 0


async def test_report_puts_each_holding_in_the_owners_context():
    report = await _run()

    turn = next(item for item in report["items"] if item["ticker"] == "TURN.L")
    assert turn["context"]["market_value_gbp"] == 15000.0
    assert turn["context"]["portfolio_share"] == 0.15
    assert turn["context"]["gain_gbp"] == -1000.0
    assert "capital gains tax" in turn["context"]["cgt_note"]
    beta = next(item for item in report["items"] if item["ticker"] == "BETA.L")
    assert "no capital gains tax" in beta["context"]["cgt_note"]
    assert turn["investigation"]["evidence"][-1]["source"] == "rns"


async def test_report_is_stored_and_the_next_run_does_not_reflag():
    first = await _run()
    second = await _run()

    assert storage.load_latest("alex")["run_date"] == "2025-03-07"
    assert len(first["items"]) == 4
    assert second["items"] == []
    assert second["not_flagged"] == 5


async def test_muted_holding_is_kept_but_listed_last():
    storage.set_muted("alex", "turn.l", True)

    report = await _run()

    assert report["items"][-1]["ticker"] == "TURN.L"
    assert report["items"][-1]["muted"] is True
    assert report["mutes"] == ["TURN.L"]


async def test_alert_lists_unmuted_holdings_without_trade_language(monkeypatch):
    sent = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda text: sent.append(text))
    storage.set_muted("alex", "BETA.L", True)

    report = await _run(notify=True)

    assert sent == [alert_text(report)]
    assert "TURN.L: Idiosyncratic deterioration" in sent[0]
    assert "BETA.L" not in sent[0]
    assert prompt.advice_phrases(sent[0]) == []


def test_holdings_skip_cash_and_combine_accounts():
    holdings = holdings_by_ticker(PORTFOLIO)

    assert "CASH.GBP" not in holdings
    assert [a["tax_free"] for a in holdings["TURN.L"]["accounts"]] == [True, False]
    assert holdings["UP.L"]["gain_pct"] == 1.0


async def test_investigation_is_capped_per_run():
    report = await _run(cfg=TrendWatchConfig(max_investigated=1))

    statuses = {item["ticker"]: item["investigation"]["status"] for item in report["items"]}
    assert statuses["TURN.L"] == "ok"
    assert statuses["BETA.L"] == "not_run"
    beta = next(item for item in report["items"] if item["ticker"] == "BETA.L")
    assert "only the top 1" in beta["investigation"]["notes"][0]
    assert beta["verdict"] == prompt.VERDICT_MARKET


async def test_pence_cliff_with_no_open_issue_is_a_data_problem_end_to_end():
    # load_issues reports nothing for JEGI.L: the verdict comes from the detector's own artefact check.
    report = await _run(load_issues=lambda: ([], []))

    jegi = next(item for item in report["items"] if item["ticker"] == "JEGI.L")
    assert jegi["verdict"] == prompt.VERDICT_DATA
    assert jegi["detection"]["artefacts"][0]["kind"] == "price_scale_step"
    assert [issue["type"] for issue in jegi["data_issues"]] == ["PRICE_SCALE_SUSPECT"]
    assert jegi["investigation"]["status"] == "skipped"
