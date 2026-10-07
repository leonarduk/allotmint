"""Historical stress test across strategies (#9824)."""

from __future__ import annotations

import datetime as dt

import pytest

from backend.common import strategy_stress
from backend.common.strategies import Strategy, create_strategy
from backend.timeseries.total_return import PRICE_RETURN_BASIS, TOTAL_RETURN_BASIS

EVENT_DATE = dt.date(2020, 2, 19)
HORIZONS = {"1m": 30, "1y": 365}

# Stand-in ticker -> ({horizon: return}, basis). Anything absent has no prices.
SERIES = {
    "VWRL.L": ({"1m": -0.20, "1y": 0.05}, TOTAL_RETURN_BASIS),
    "IGLT.L": ({"1m": 0.02, "1y": -0.01}, TOTAL_RETURN_BASIS),
    # Gold has no dividends file, so the loader reports price basis.
    "PHAU.L": ({"1m": 0.04, "1y": 0.10}, PRICE_RETURN_BASIS),
    "SLXX.L": ({"1m": -0.05, "1y": 0.02}, PRICE_RETURN_BASIS),
    # Long gilts have the 1m close but not the 1y one.
    "GLTL.L": ({"1m": 0.03, "1y": None}, TOTAL_RETURN_BASIS),
}


@pytest.fixture(autouse=True)
def fake_series(monkeypatch):
    calls: list[str] = []

    def fake(ticker, event_date, horizons):
        calls.append(ticker)
        assert event_date == EVENT_DATE
        returns, basis = SERIES.get(ticker, ({}, TOTAL_RETURN_BASIS))
        return {label: returns.get(label) for label in horizons}, basis

    monkeypatch.setattr(strategy_stress, "instrument_forward_returns", fake)
    monkeypatch.setattr(strategy_stress, "PRO_SLEEVE_RETURNS", None)
    return calls


def _row(targets):
    strategy = Strategy(id="s", name="S", targets=targets)
    needed = {s: strategy_stress.sleeve_returns(s, EVENT_DATE, HORIZONS) for s in targets}
    return strategy_stress.strategy_result(strategy, needed, HORIZONS)


def test_weighted_return_with_weights_fixed_at_the_event():
    row = _row({"equity": 60.0, "intermediate_gilts": 40.0})
    assert row["horizons"]["1m"] == {
        "return_pct": -11.2,  # 60 * -0.20 + 40 * 0.02
        "coverage_pct": 100.0,
        "return_basis": TOTAL_RETURN_BASIS,
        "missing": [],
    }
    assert row["horizons"]["1y"]["return_pct"] == 2.6
    assert row["series"] == {"equity": ["VWRL.L"], "intermediate_gilts": ["IGLT.L"]}


def test_cash_is_held_flat():
    row = _row({"equity": 50.0, "cash": 50.0})
    assert row["horizons"]["1m"]["return_pct"] == -10.0
    assert row["series"]["cash"] == [strategy_stress.CASH_SERIES]


def test_price_only_series_marks_the_horizon_price_basis():
    row = _row({"equity": 80.0, "corporate_bonds": 20.0})
    assert row["horizons"]["1m"]["return_basis"] == PRICE_RETURN_BASIS


def test_gold_pays_no_income_so_its_price_return_is_total_return():
    row = _row({"equity": 80.0, "gold": 20.0})
    assert row["horizons"]["1m"]["return_basis"] == TOTAL_RETURN_BASIS
    assert row["horizons"]["1m"]["return_pct"] == -15.2


def test_sleeve_without_stand_in_gives_no_number_and_is_named():
    row = _row({"equity": 70.0, "property": 30.0})
    assert row["horizons"]["1m"] == {
        "return_pct": None,
        "coverage_pct": 70.0,
        "return_basis": None,
        "missing": ["property"],
    }
    assert row["series"]["property"] == []


def test_missing_horizon_is_per_horizon():
    row = _row({"equity": 50.0, "long_gilts": 50.0})
    assert row["horizons"]["1m"]["return_pct"] == -8.5
    assert row["horizons"]["1y"]["return_pct"] is None
    assert row["horizons"]["1y"]["missing"] == ["long_gilts"]


def test_falls_back_along_the_stand_in_chain(monkeypatch):
    monkeypatch.setitem(SERIES, "VWRL.L", ({}, TOTAL_RETURN_BASIS))
    monkeypatch.setitem(SERIES, "IOO.N", ({"1m": -0.10, "1y": 0.0}, TOTAL_RETURN_BASIS))
    row = _row({"equity": 100.0})
    assert row["horizons"]["1m"]["return_pct"] == -10.0
    assert row["series"]["equity"] == ["IOO.N"]


def test_brunner_covers_equity_before_2000(monkeypatch):
    monkeypatch.setitem(SERIES, "VWRL.L", ({}, TOTAL_RETURN_BASIS))
    monkeypatch.setitem(SERIES, "BUT.L", ({"1m": -0.25, "1y": -0.15}, TOTAL_RETURN_BASIS))
    row = _row({"equity": 100.0})
    assert row["horizons"]["1m"]["return_pct"] == -25.0
    assert row["series"]["equity"] == ["BUT.L"]


def test_pro_fills_only_what_stand_ins_cannot(monkeypatch):
    seen = []

    def pro(sleeve, event_date, horizons):
        seen.append(sleeve)
        return {"1m": 0.99, "1y": 0.07}, TOTAL_RETURN_BASIS, "synthetic 20y gilt"

    monkeypatch.setattr(strategy_stress, "PRO_SLEEVE_RETURNS", pro)
    row = _row({"equity": 50.0, "long_gilts": 50.0})
    assert seen == ["long_gilts"]  # equity was fully covered, so pro was not asked
    assert row["horizons"]["1m"]["return_pct"] == -8.5  # GLTL.L kept for 1m
    assert row["horizons"]["1y"]["return_pct"] == 6.0  # 50 * 0.05 + 50 * 0.07
    assert row["series"]["long_gilts"] == ["GLTL.L", "synthetic 20y gilt"]


def test_a_failing_pro_hook_is_logged_and_the_stand_ins_still_answer(monkeypatch, caplog):
    def broken(sleeve, event_date, horizons):
        raise IndexError("index 0 is out of bounds")

    monkeypatch.setattr(strategy_stress, "PRO_SLEEVE_RETURNS", broken)
    with caplog.at_level("WARNING"):
        row = _row({"equity": 50.0, "long_gilts": 50.0})
    assert row["horizons"]["1m"]["return_pct"] == -8.5  # stand-ins answered 1m
    assert row["horizons"]["1y"]["missing"] == ["long_gilts"]  # pro could not fill 1y
    assert "allotmint-pro sleeve returns failed for long_gilts" in caplog.text


def test_stress_strategies_lists_builtins_and_user_strategies(tmp_path, monkeypatch, fake_series):
    (tmp_path / "alex").mkdir()
    create_strategy("alex", {"name": "Mine", "targets": {"equity": 90, "gold": 10}}, tmp_path)
    monkeypatch.setattr(strategy_stress, "portfolio_result", lambda *a: {"baseline_total_value_gbp": 1.0})
    event = {"id": "covid", "name": "Covid", "date": "2020-02-19", "proxy_index": "SPY.N"}

    out = strategy_stress.stress_strategies("alex", event, HORIZONS, tmp_path)

    names = [row["name"] for row in out["strategies"]]
    assert names[0] == "60/40" and names[-1] == "Mine"
    assert out["strategies"][-1]["horizons"]["1m"]["return_pct"] == -17.6
    assert out["event"] == {"id": "covid", "name": "Covid", "date": "2020-02-19"}
    assert out["horizons"] == ["1m", "1y"]
    assert out["portfolio"] == {"baseline_total_value_gbp": 1.0}
    assert len(fake_series) == len(set(fake_series))  # each stand-in loaded once


def test_portfolio_result_matches_the_holdings_scenario(monkeypatch):
    portfolio = {"total_value_estimate_gbp": 1000.0, "accounts": []}
    monkeypatch.setattr(strategy_stress, "build_owner_portfolio", lambda owner, root: portfolio)

    def fake_event(pf, event, horizons):
        assert pf is portfolio and event["date"] == "2020-02-19"
        return {
            "1m": {"delta_gbp": -150.0, "coverage_pct": 92.0, "return_basis": "total"},
            "1y": {"delta_gbp": None, "coverage_pct": 10.0, "return_basis": None},
        }

    monkeypatch.setattr(strategy_stress, "apply_historical_event_portfolio", fake_event)
    out = strategy_stress.portfolio_result("alex", {"date": "2020-02-19"}, HORIZONS, None)
    assert out["baseline_total_value_gbp"] == 1000.0
    assert out["horizons"]["1m"] == {"return_pct": -15.0, "coverage_pct": 92.0, "return_basis": "total", "missing": []}
    assert out["horizons"]["1y"]["return_pct"] is None


def test_portfolio_result_none_without_account_data(monkeypatch):
    def missing(owner, root):
        raise FileNotFoundError(owner)

    monkeypatch.setattr(strategy_stress, "build_owner_portfolio", missing)
    assert strategy_stress.portfolio_result("ghost", {"date": "2020-02-19"}, HORIZONS, None) is None
