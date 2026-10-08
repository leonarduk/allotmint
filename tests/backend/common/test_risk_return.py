"""Return vs volatility points for the dashboard chart (backend.common.risk_return)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.common import ledger_performance as lp
from backend.common import risk_return as rr

END = date(2026, 2, 27)  # a Friday, so the reporting date is END itself
DAYS = 60

# Two accounts in one GBP instrument whose close alternates +2%/-1% daily.
_DAYS = pd.bdate_range("2025-12-01", END)
_CLOSES = pd.Series(
    100.0 * np.cumprod([1.0] + [1.02 if i % 2 else 0.99 for i in range(1, len(_DAYS))]),
    index=_DAYS,
)


def _ledger(account: str, start: str, units: int) -> lp.AccountLedger:
    price = float(_CLOSES[pd.Timestamp(start)])
    cost = round(units * price * 100)
    return lp.AccountLedger(
        account,
        [
            {"date": start, "type": "DEPOSIT", "amount_minor": cost},
            {"date": start, "type": "BUY", "ticker": "AAA.L", "units": units, "amount_minor": cost},
        ],
        True,
    )


LEDGERS = {"alice": [_ledger("isa", "2026-01-05", 10), _ledger("sipp", "2026-01-20", 5)]}


@pytest.fixture
def fake_data(monkeypatch):
    calls: list[tuple[str, date, date]] = []

    def load(key, start, end):
        calls.append((key, start, end))
        window = _CLOSES[(_CLOSES.index >= pd.Timestamp(start)) & (_CLOSES.index <= pd.Timestamp(end))]
        return window if key == "AAA.L" else pd.Series(dtype=float)

    monkeypatch.setattr(lp, "load_gbp_closes", load)
    monkeypatch.setattr(lp, "load_owner_ledgers", lambda owner: list(LEDGERS.get(owner, [])))
    monkeypatch.setattr(rr.portfolio_mod, "build_owner_portfolio", lambda owner, pricing_date=None: {"accounts": []})
    monkeypatch.setattr(rr.group_portfolio, "group_members", lambda slug: ["alice", "bob"])
    return calls


def _expected(ledgers):
    perf = lp.build_ledger_performance(ledgers, END, price_loader=lambda k, s, e: _CLOSES)
    return rr.stats_from_returns(perf.returns, END - timedelta(days=DAYS), END)


def test_group_owner_and_account_points(fake_data):
    result = rr.compute_group_risk_return("family", DAYS, pricing_date=END)

    assert result["missing_members"] == ["bob"]
    assert result["end"] == END.isoformat()
    kinds = [(p["kind"], p["owner"], p["account"]) for p in result["points"]]
    assert kinds == [
        ("group", None, None),
        ("owner", "alice", None),
        ("account", "alice", "isa"),
        ("account", "alice", "sipp"),
    ]

    isa = _expected([LEDGERS["alice"][0]])
    isa_point = result["points"][2]
    assert isa_point["period_return"] == pytest.approx(isa.period_return)
    assert isa_point["volatility"] == pytest.approx(isa.volatility)
    # Only alice has a ledger, so the group is exactly alice.
    assert result["points"][0]["period_return"] == pytest.approx(result["points"][1]["period_return"])


def test_windows_under_a_year_are_not_annualised(fake_data):
    result = rr.compute_group_risk_return("family", DAYS, pricing_date=END)

    sipp = result["points"][3]
    assert sipp["volatility"] > 0
    assert sipp["annualised_return"] is None


def test_too_few_days_has_no_volatility(fake_data):
    LEDGERS["late"] = [_ledger("isa", "2026-02-20", 1)]
    try:
        stats = _expected(LEDGERS["late"])
    finally:
        del LEDGERS["late"]

    # Under MIN_OBSERVATIONS_FOR_RISK days of history: noise, so no figure.
    assert stats.volatility is None
    assert stats.period_return is not None


def test_prices_load_once_per_instrument(fake_data):
    rr.compute_group_risk_return("family", DAYS, pricing_date=END)

    # isa replays from 5 Jan, sipp from 20 Jan, owner and group from 5 Jan:
    # the first (widest) load serves every later rebuild.
    assert [call[0] for call in fake_data] == ["AAA.L"]


def test_unknown_group_raises(monkeypatch):
    def unknown(slug):
        raise ValueError(slug)

    monkeypatch.setattr(rr.group_portfolio, "group_members", unknown)
    with pytest.raises(ValueError):
        rr.compute_group_risk_return("nope", DAYS, pricing_date=END)


def test_benchmark_rebases_on_close_before_window(monkeypatch):
    monkeypatch.setattr(rr, "_index_closes", lambda symbol, start, end: _CLOSES)

    result = rr.compute_benchmark_risk_return("^FTSE", DAYS, pricing_date=END)

    after = END - timedelta(days=DAYS)
    base = _CLOSES[_CLOSES.index <= pd.Timestamp(after)].iloc[-1]
    assert result is not None
    assert result["ticker"] == "^FTSE"
    assert result["period_return"] == pytest.approx(_CLOSES.iloc[-1] / base - 1)
    daily = _CLOSES[_CLOSES.index > pd.Timestamp(after) - pd.Timedelta(days=7)].pct_change().dropna()
    daily = daily[daily.index > pd.Timestamp(after)]
    assert result["volatility"] == pytest.approx(daily.std(ddof=1) * math.sqrt(252))


def test_benchmark_without_closes_is_none(monkeypatch):
    monkeypatch.setattr(lp, "load_gbp_closes", lambda key, start, end: pd.Series(dtype=float))

    assert rr.compute_benchmark_risk_return("XYZ.L", DAYS, pricing_date=END) is None


def test_non_index_benchmark_uses_cached_gbp_closes(monkeypatch):
    seen = []

    def load(key, start, end):
        seen.append(key)
        return _CLOSES

    monkeypatch.setattr(lp, "load_gbp_closes", load)
    monkeypatch.setattr(rr, "_index_closes", lambda *a: pytest.fail("index path used for a listed ticker"))

    assert rr.compute_benchmark_risk_return("VWRL.L", DAYS, pricing_date=END) is not None
    assert seen == ["VWRL.L"]


def test_index_closes_are_cached_only_when_present(monkeypatch):
    downloads = []

    def download(symbol, start, end):
        downloads.append(symbol)
        return _CLOSES if symbol == "^FTSE" else pd.Series(dtype=float)

    monkeypatch.setattr(rr, "_download_index_closes", download)
    monkeypatch.setattr(rr, "_INDEX_CLOSES", {})
    start = END - timedelta(days=DAYS)

    rr._index_closes("^FTSE", start, END)
    rr._index_closes("^FTSE", start, END)
    rr._index_closes("^BAD", start, END)
    rr._index_closes("^BAD", start, END)

    assert downloads == ["^FTSE", "^BAD", "^BAD"]
