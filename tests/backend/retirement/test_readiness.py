"""The monitor's run(owner) end to end on synthetic data (#10484): forecast reuse, history, attribution."""

from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from backend.common import investment_plan as plan_mod
from backend.common import pension as pension_common
from backend.retirement import agent, history, readiness
from backend.routes import pension as pension_route

DOB = "1975-06-15"
PLAN = {
    "owner": "alex",
    "updated": "2029-12-01",
    "target": [{"class": "cash", "weight_pct": 40}, {"class": "equity", "weight_pct": 60}],
}
SETTINGS = {"death_age": 80, "retirement_age": 60, "state_pension_annual": 5000.0, "survival_levels": [95.0, 100.0]}


def _tx(day: str, pence: float, type_: str = "DEPOSIT", account: str = "SIPP") -> SimpleNamespace:
    return SimpleNamespace(owner="alex", account=account, type=type_, date=day, amount_minor=pence)


@pytest.fixture()
def env(monkeypatch, tmp_path, synthetic_history):
    accounts = tmp_path / "accounts"
    (accounts / "alex").mkdir(parents=True)
    (accounts / "alex" / "person.json").write_text(json.dumps({"owner": "alex", "dob": DOB}))
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "alex.json").write_text(json.dumps(PLAN))
    monkeypatch.setattr(plan_mod.config, "accounts_root", accounts, raising=False)
    monkeypatch.setenv(history.STORE_ENV, str(tmp_path / "store"))
    monkeypatch.setattr(agent, "_default_llm", lambda: None)
    monkeypatch.setattr(readiness, "_latest_gilt_yield", lambda: {"date": "2030-01-14", "pct": 4.1})
    state = {"pot": 100000.0, "transactions": []}
    monkeypatch.setattr(
        pension_route,
        "build_owner_portfolio",
        lambda owner, **_: {"accounts": [{"account_type": "sipp", "value_estimate_gbp": state["pot"]}]},
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts_root=accounts)))

    class _RunDay(dt.date):
        """The route's forecast reads ``date.today()``; pin it to the simulated run day."""

        @classmethod
        def today(cls):
            return state["today"]

    monkeypatch.setattr(pension_common, "dt", SimpleNamespace(date=_RunDay, datetime=dt.datetime))

    def go(day: dt.date, **overrides):
        state["today"] = day
        return readiness.run(
            "alex",
            overrides={**SETTINGS, **overrides},
            request=request,
            today=day,
            long_history=synthetic_history,
            load_transactions=lambda: state["transactions"],
        )

    return SimpleNamespace(state=state, run=go, store=tmp_path / "store")


def test_run_reuses_forecast_and_stores_report(env):
    report = env.run(dt.date(2030, 1, 15))
    assert report["forecast"]["pension_pot_gbp"] == 100000.0
    # The simulation's projection is the forecast's own projection.
    assert report["results"]["projection"]["projected_pot_nominal_gbp"] == pytest.approx(
        report["forecast"]["projected_pot_gbp"], abs=0.01
    )
    projection = report["results"]["projection"]
    assert projection["years_to_retirement"] == 6
    assert projection["start_pot_real_gbp"] == pytest.approx(
        projection["projected_pot_nominal_gbp"] / 1.02**6, abs=0.01
    )
    simulation = report["results"]["simulation"]
    assert simulation["horizon_years"] == 20
    assert simulation["windows"]["count"] == 11  # 1990..2000 start years; later ones run past 2019
    assert simulation["state_pension_from_year"] == report["forecast"]["state_pension_age"] - 60
    assert report["headline"]["survival_pct"] == 95.0
    assert report["headline"]["income_gbp"] > 0
    assert report["results"]["mapping"]["proxy_share_pct"] == 60.0
    assert report["attribution"] is None
    assert report["narrative"]["source"] == "template"
    assert readiness.ADVISER_NOTE in report["caveats"]
    assert any("Return basis" in c and "#9370" in c for c in report["caveats"])
    assert any("proxy series" in c for c in report["caveats"])
    assert report["digest_items"][0]["kind"] == "fact"
    assert history.latest_run("alex")["run_date"] == "2030-01-15"
    assert (env.store / "alex.json").exists()


def test_extra_contribution_with_unchanged_markets_is_all_contributions(env):
    first = env.run(dt.date(2030, 1, 15))
    env.state["pot"] = 110000.0
    env.state["transactions"] = [
        _tx("2030-02-01", 1_000_000),
        _tx("2030-01-10", 999_999),  # before the previous run: not counted
        _tx("2030-02-02", 500_000, account="ISA"),  # not a pension account
    ]
    second = env.run(dt.date(2030, 4, 15))
    change = second["attribution"]
    assert change["previous_run_date"] == "2030-01-15"
    assert change["flows_since_previous_gbp"] == 10000.0
    assert change["change_gbp"] > 0
    assert change["change_gbp"] == pytest.approx(second["headline"]["income_gbp"] - first["headline"]["income_gbp"])
    assert change["parts_gbp"] == {
        "data_revision": 0.0,
        "contributions": change["change_gbp"],
        "markets": 0.0,
        "assumptions": 0.0,
    }
    assert second["assumption_changes"] == []


def test_pot_growth_without_flows_is_markets(env):
    env.run(dt.date(2030, 1, 15))
    env.state["pot"] = 90000.0
    second = env.run(dt.date(2030, 4, 15))
    parts = second["attribution"]["parts_gbp"]
    assert parts["contributions"] == 0.0 and parts["assumptions"] == 0.0
    assert parts["markets"] == second["attribution"]["change_gbp"] < 0


def test_changed_assumptions_are_flagged_and_attributed(env):
    env.run(dt.date(2030, 1, 15))
    second = env.run(dt.date(2030, 4, 15), retirement_age=62)
    labels = [c["label"] for c in second["assumption_changes"]]
    assert "retirement age" in labels
    parts = second["attribution"]["parts_gbp"]
    assert parts["contributions"] == 0.0 and parts["markets"] == 0.0
    assert parts["assumptions"] == second["attribution"]["change_gbp"] != 0


def test_settings_carry_over_from_previous_run(env):
    env.run(dt.date(2030, 1, 15), floor_gbp=50000.0)
    second = readiness.ReadinessSettings.resolve({}, history.latest_run("alex"))
    assert second.floor_gbp == 50000.0 and second.retirement_age == 60


def test_cpi_flag_when_assumption_differs(env):
    report = env.run(dt.date(2030, 1, 15), assumed_inflation_pct=4.0)
    assert report["market"]["uk_cpi"] == {"year": 2019, "pct": 2.0}
    assert report["market"]["flags"] and "4.0% assumed" in report["market"]["flags"][0]
    assert report["market"]["gilt_10y_yield"] == {"date": "2030-01-14", "pct": 4.1}


def test_missing_plan_is_readiness_error(env, tmp_path):
    (tmp_path / "plans" / "alex.json").unlink()
    with pytest.raises(readiness.ReadinessError, match="no investment plan"):
        env.run(dt.date(2030, 1, 15))


def test_same_day_rerun_replaces_report(env):
    env.run(dt.date(2030, 1, 15))
    env.state["pot"] = 120000.0
    env.run(dt.date(2030, 1, 15))
    runs = history.load_runs("alex")
    assert len(runs) == 1 and runs[0]["inputs"]["pot_gbp"] == 120000.0


def test_invalid_survival_levels_rejected():
    with pytest.raises(ValueError):
        readiness.ReadinessSettings.resolve({"survival_levels": [0]}, None)


def test_pension_flows_signs_and_window():
    rows = [
        _tx("2030-02-01", 10000),
        _tx("2030-02-02", 2500, type_="WITHDRAWAL"),
        _tx("2030-02-03", 4000, type_="TRANSFER_IN"),
        _tx("2030-02-04", 9999, type_="BUY"),
        _tx("not-a-date", 9999),
    ]
    total = readiness.pension_flows_between(rows, "alex", dt.date(2030, 1, 31), dt.date(2030, 2, 28))
    assert total == pytest.approx((10000 - 2500 + 4000) / 100)


def test_invalid_owner_rejected_by_store():
    with pytest.raises(ValueError):
        history.load_runs("../etc")


def test_storage_failure_is_reported_not_raised(env, monkeypatch):
    def fail(owner, run):
        raise OSError("read-only file system")

    monkeypatch.setattr(history, "save_run", fail)
    report = env.run(dt.date(2030, 1, 15))
    assert report["storage"]["stored"] is False
    assert "read-only" in report["storage"]["reason"]
    assert report["headline"]["income_gbp"] > 0
