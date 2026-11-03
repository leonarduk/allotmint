"""Dashboard cumulative return on the ledger total-return basis (#10128).

``/performance/{owner}`` used to report a price-only return of today's
holdings, so interest and dividends never showed. It now reports the ledger
chained return (the basis of /twr, /total-return and the reports), keeps the
old figure as ``price_return``, and leaves value and drawdown alone.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.common import ledger_performance as lp
from backend.common import portfolio_utils as pu

END = date(2026, 3, 31)
DATES = ["2026-03-02", "2026-03-03", "2026-03-16", "2026-03-31"]


def _flat_history(value=10_000.0):
    """The current-holdings result for a flat £10,000 portfolio: price-only return 0, no drawdown."""
    return {
        "history": [
            {"date": day, "value": value, "cumulative_return": 0.0, "running_max": value, "drawdown": 0.0}
            for day in DATES
        ],
        "max_drawdown": 0.0,
        "reporting_date": DATES[-1],
        "previous_date": DATES[-2],
        "data_quality_issues": [],
    }


def _income_ledger(income_type):
    """£10,000 deposited before the window, then £100 of ``income_type`` inside it."""
    transactions = [
        {"date": "2026-02-02", "type": "DEPOSIT", "amount_minor": 1_000_000},
        {"date": "2026-03-16", "type": income_type, "amount_minor": 10_000},
    ]
    ledger = lp.AccountLedger("isa", transactions, trade_cash=True)
    return lp.build_ledger_performance([ledger], END, price_loader=lambda key, start, end: pd.Series(dtype=float))


@pytest.fixture
def current(monkeypatch):
    result = _flat_history()
    monkeypatch.setattr(pu, "_current_holdings_performance", lambda *a, **k: result)
    return result


def _rebuilt(monkeypatch, perf, missing=()):
    calls = []

    def fake(owner, *, group, pricing_date):
        calls.append((owner, group, pricing_date))
        return perf, list(missing)

    monkeypatch.setattr(pu, "_rebuilt_performance", fake)
    return calls


@pytest.mark.parametrize("income_type", ["INTEREST", "DIVIDEND"])
def test_cumulative_return_includes_income_and_matches_the_ledger(monkeypatch, current, income_type):
    perf = _income_ledger(income_type)
    _rebuilt(monkeypatch, perf)

    result = pu.compute_owner_performance("alice", ledger_cumulative_return=True)

    history = result["history"]
    assert history[-1]["cumulative_return"] == pytest.approx(0.01)
    assert history[-1]["cumulative_return"] == pytest.approx(
        lp.chained_return(perf.returns, date.fromisoformat(DATES[0]), END)
    )
    assert [row["cumulative_return"] for row in history[:2]] == pytest.approx([0.0, 0.0])
    # The old price-only figure is kept, and value/drawdown are untouched.
    assert [row["price_return"] for row in history] == [0.0] * 4
    assert [row["value"] for row in history] == [10_000.0] * 4
    assert [row["drawdown"] for row in history] == [0.0] * 4
    assert result["max_drawdown"] == 0.0
    assert result["cumulative_return_basis"] == pu.CUMULATIVE_RETURN_BASIS_LEDGER == "ledger_total_return"
    assert result["drawdown_basis"] == "current_holdings"
    assert result["cumulative_return_unavailable_reason"] is None


def test_owner_without_a_ledger_gets_unavailable_not_the_price_return(monkeypatch, current):
    _rebuilt(monkeypatch, None)

    result = pu.compute_owner_performance("alice", ledger_cumulative_return=True)

    assert [row["cumulative_return"] for row in result["history"]] == [None] * 4
    assert [row["price_return"] for row in result["history"]] == [0.0] * 4
    assert result["cumulative_return_basis"] == "unavailable"
    assert result["cumulative_return_unavailable_reason"] == "no_ledger"


def test_exclude_cash_is_unavailable_on_the_ledger_basis(monkeypatch, current):
    calls = _rebuilt(monkeypatch, _income_ledger("INTEREST"))

    result = pu.compute_owner_performance("alice", include_cash=False, ledger_cumulative_return=True)

    assert calls == []
    assert result["history"][-1]["cumulative_return"] is None
    assert result["cumulative_return_unavailable_reason"] == "exclude_cash"


def test_group_flags_members_without_a_ledger(monkeypatch, current):
    calls = _rebuilt(monkeypatch, _income_ledger("INTEREST"), missing=["bob"])

    result = pu.compute_owner_performance("family", group=True, pricing_date=END, ledger_cumulative_return=True)

    assert calls == [("family", True, END)]
    assert result["cumulative_return_partial"] is True
    assert result["missing_members"] == ["bob"]
    assert result["history"][-1]["cumulative_return"] == pytest.approx(0.01)


def test_default_keeps_the_price_only_basis_for_other_callers(monkeypatch, current):
    calls = _rebuilt(monkeypatch, _income_ledger("INTEREST"))

    result = pu.compute_owner_performance("alice")

    assert calls == []
    assert result is current
    assert "price_return" not in result["history"][0]


def test_a_shared_result_is_never_mutated(monkeypatch, current):
    _rebuilt(monkeypatch, _income_ledger("INTEREST"))

    pu.compute_owner_performance("alice", ledger_cumulative_return=True)

    assert current["history"][-1] == _flat_history()["history"][-1]


def test_ledger_cumulative_returns_chain_from_the_first_date():
    perf = _income_ledger("DIVIDEND")
    dates = ["2026-01-15", "2026-03-14", "2026-03-15", "2026-03-31"]  # before inception, a weekend

    returns = pu.ledger_cumulative_returns(perf, dates)

    assert returns == pytest.approx([0.0, 0.0, 0.0, 0.01])
    for day, value in zip(dates, returns):
        expected = lp.chained_return(perf.returns, date.fromisoformat(dates[0]), date.fromisoformat(day)) or 0.0
        assert value == pytest.approx(expected)
    assert pu.ledger_cumulative_returns(perf, []) == []


# ---- routes ----------------------------------------------------------------


@pytest.fixture
def client():
    from backend.app import create_app

    return TestClient(create_app())


def test_owner_route_uses_the_ledger_basis(client, monkeypatch, current):
    _rebuilt(monkeypatch, _income_ledger("INTEREST"))
    monkeypatch.setattr(pu, "compute_max_drawdown", lambda *a, **k: (0.0, {}))

    body = client.get("/performance/alice").json()
    max_dd = client.get("/performance/alice/max-drawdown").json()

    assert body["history"][-1]["cumulative_return"] == pytest.approx(0.01)
    assert body["history"][-1]["price_return"] == 0.0
    assert body["cumulative_return_basis"] == "ledger_total_return"
    # Drawdown stays on the current-holdings series shared with /max-drawdown (#7786).
    assert body["drawdown_basis"] == "current_holdings"
    assert body["max_drawdown"] == max_dd["max_drawdown"]


def test_group_route_uses_the_ledger_basis(client, monkeypatch, current):
    calls = _rebuilt(monkeypatch, _income_ledger("DIVIDEND"))

    body = client.get("/performance-group/family").json()

    assert calls and calls[0][:2] == ("family", True)
    assert body["history"][-1]["cumulative_return"] == pytest.approx(0.01)
    assert body["cumulative_return_basis"] == "ledger_total_return"
