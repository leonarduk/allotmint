"""Capture: qualifying changes, pre-filled drafts and the read-only tool allowlist (#10481)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.common.investment_plan import InvestmentPlan
from backend.decision_journal import capture
from backend.decision_journal.capture import (
    READ_ONLY_CONTEXT_TOOLS,
    ContextTools,
    default_context_tools,
    plan_change_draft,
    qualifying_trades,
    trade_amount_gbp,
    trade_change,
    trade_draft,
)
from tests.backend.decision_journal.fixtures import fake_series

TXS = [
    {
        "id": "alex:isa:7",
        "owner": "alex",
        "account": "isa",
        "date": "2026-10-01",
        "type": "SELL",
        "ticker": "aaa.l",
        "units": 100,
        "price_gbp": 100.0,
    },
    {
        "id": "alex:isa:8",
        "owner": "alex",
        "account": "isa",
        "date": "2026-10-02",
        "type": "BUY",
        "ticker": "BBB.L",
        "units": 5,
        "price_gbp": 50.0,
    },  # £250: below the threshold
    {
        "id": "alex:isa:9",
        "owner": "alex",
        "account": "isa",
        "date": "2026-10-03",
        "type": "DIVIDEND",
        "ticker": "AAA.L",
        "units": 1,
        "price_gbp": 5000.0,
    },
    {
        "id": "alex:isa:1",
        "owner": "alex",
        "account": "isa",
        "date": "2026-01-01",
        "type": "BUY",
        "ticker": "AAA.L",
        "units": 100,
        "price_gbp": 100.0,
    },  # outside the window
]


def _window(**overrides):
    args = {"threshold_gbp": 1000.0, "handled_refs": set(), "since": date(2026, 9, 9), "until": date(2026, 10, 9)}
    return {**args, **overrides}


def test_qualifying_trades_filters_size_type_and_window():
    found = qualifying_trades(TXS, **_window())
    assert [c["source_ref"] for c in found] == ["alex:isa:7"]
    assert found[0] == {
        "source_ref": "alex:isa:7",
        "date": "2026-10-01",
        "type": "SELL",
        "ticker": "AAA.L",
        "account": "isa",
        "amount_gbp": 10_000.0,
        "price_gbp": 100.0,
    }


def test_trade_amount_treats_zero_units_as_zero_and_falls_back_to_shares_only_when_units_is_absent():
    # units=0 is a recorded value (a zero-size trade), not "unset": it never qualifies.
    assert trade_amount_gbp({"units": 0, "shares": 50, "price_gbp": 10.0}) == 0.0
    assert trade_amount_gbp({"shares": 50, "price_gbp": 10.0}) == 500.0
    assert trade_amount_gbp({"units": 5}) is None


def test_qualifying_trades_threshold_is_configurable_and_skips_handled():
    assert {c["source_ref"] for c in qualifying_trades(TXS, **_window(threshold_gbp=100))} == {
        "alex:isa:7",
        "alex:isa:8",
    }
    assert qualifying_trades(TXS, **_window(handled_refs={"alex:isa:7"})) == []


def _tools():
    return ContextTools(
        {
            "get_allocation": lambda: {"total_value_gbp": 100_000.0, "values_gbp": {"AAA.L": 20_000.0}},
            "get_live_prices": lambda tickers: {t: 101.0 for t in tickers},
            "get_instrument_technicals": lambda ticker: {"return_3m_pct": -4.0},
        }
    )


PLAN = InvestmentPlan.model_validate(
    {
        "owner": "alex",
        "updated": "2026-10-01",
        "target": [{"class": "equity", "weight_pct": 100}],
        "vehicles": {"equity": ["AAA.L"]},
    }
)


def test_sell_draft_is_prefilled_with_facts_and_leaves_reasoning_blank():
    draft = trade_draft(trade_change(TXS[0]), _tools(), plan=PLAN, today=date(2026, 10, 9))
    assert draft["decision"] == "Sold £10,000 of AAA.L"
    assert draft["reason"] == ""
    assert draft["amount_gbp"] == 10_000.0
    assert draft["alternatives"] == ["Keep holding AAA.L"]
    assert draft["legs"][0] == {"role": "chosen", "label": "Proceeds held as cash", "ticker": None}
    snap = draft["snapshot"]
    assert snap["instrument"] == "AAA.L"
    assert snap["plan_class"] == "equity"
    # SELL: current £20k of £100k = 20%; before = (20k + 10k) / 100k = 30%.
    assert snap["weights"]["before_pct"] == 30.0 and snap["weights"]["after_pct"] == 20.0
    assert snap["latest_prices"] == {"AAA.L": 101.0}
    assert snap["technicals"] == {"return_3m_pct": -4.0}
    assert "valuation" not in snap  # no provider configured
    assert draft["id"].startswith("dj-")


def _tools_holding(values):
    return ContextTools({"get_allocation": lambda: {"total_value_gbp": 100_000.0, "values_gbp": values}})


def test_buy_draft_legs_compare_with_keeping_cash():
    # Already held £5,000 of BBB and bought £2,500 more: £7,500 now, so £5,000 (5%) before.
    draft = trade_draft(trade_change({**TXS[1], "units": 50}), _tools_holding({"BBB.L": 7_500.0}))
    assert draft["decision"] == "Bought £2,500 of BBB.L"
    assert [leg["ticker"] for leg in draft["legs"]] == ["BBB.L", None]
    assert draft["snapshot"]["weights"]["before_pct"] == 5.0
    assert draft["snapshot"]["weights"]["after_pct"] == 7.5


def test_buy_larger_than_current_holding_leaves_before_weight_unknown():
    # £2,500 bought but only £1,000 held now (sold since, or fell): the earlier weight can't be derived.
    draft = trade_draft(trade_change({**TXS[1], "units": 50}), _tools_holding({"BBB.L": 1_000.0}))
    assert draft["snapshot"]["weights"]["before_pct"] is None
    assert draft["snapshot"]["weights"]["after_pct"] == 1.0


def test_plan_change_draft_describes_target_diff():
    draft = plan_change_draft({"equity": 60, "long_gilts": 40}, {"equity": 50, "long_gilts": 50}, on=date(2026, 10, 9))
    assert draft["decision"] == "Changed plan target: equity 60% → 50%, long_gilts 40% → 50%"
    assert draft["reason"] == ""
    assert plan_change_draft({"equity": 100}, {"equity": 100}) is None


def test_context_tool_allowlist_is_read_only():
    assert READ_ONLY_CONTEXT_TOOLS == {
        "get_live_prices",
        "get_instrument_technicals",
        "get_instrument_valuation",
        "get_allocation",
    }
    assert all(name.startswith("get_") for name in READ_ONLY_CONTEXT_TOOLS)


@pytest.mark.parametrize("name", ["save_plan", "post_transaction", "update_allocation_policy"])
def test_context_tools_refuse_anything_outside_the_allowlist(name):
    with pytest.raises(ValueError, match="Not read-only"):
        ContextTools({name: lambda: None})
    with pytest.raises(PermissionError):
        _tools().call(name)


def test_default_tools_compute_technicals_from_stored_closes(monkeypatch):
    monkeypatch.setattr(capture, "_allocation", lambda owner, root: {"total_value_gbp": 0.0, "values_gbp": {}})
    tools = default_context_tools("alex", None, load_series=fake_series, today=date(2026, 7, 2))
    technicals = tools.call("get_instrument_technicals", ticker="AAA.L")
    assert technicals["return_basis"] == "total"
    assert technicals["return_3m_pct"] == pytest.approx(-5.26)  # 90 / 95 - 1
    assert tools.call("get_live_prices", tickers=["AAA.L"]) == {"AAA.L": 90.0}
    assert tools.call("get_instrument_valuation", ticker="AAA.L") is None
