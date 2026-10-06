"""Model, validation and storage of the per-owner investment plan (#9547)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.common import investment_plan as plan_mod
from backend.common.allocation_policy import AllocationPolicy
from backend.common.investment_plan import (
    PLAN_CLASSES,
    PlanNotFoundError,
    compare_with_rebalance_targets,
    load_plan,
    parse_plan,
    save_plan,
    vehicle_warnings,
)


def plan_data(**overrides):
    data = {
        "owner": "alex",
        "version": 1,
        "updated": "2026-10-06",
        "status": "draft",
        "summary": "40/20/20/20",
        "target": [
            {"class": "equity", "weight_pct": 40},
            {"class": "long_gilts", "weight_pct": 10},
            {"class": "intermediate_gilts", "weight_pct": 10},
            {"class": "short_gilts", "weight_pct": 20},
            {"class": "gold", "weight_pct": 20},
        ],
        "vehicles": {
            "long_gilts": ["GLTL.L"],
            "equity": [{"note": "global equity fund to be chosen"}],
        },
        "assumptions": [{"key": "retirement_age", "value": 58, "note": "about 2033"}],
        "decisions": [{"date": "2026-10-06", "decision": "No small-value", "alternatives": ["GB"], "reason": "x"}],
        "open_questions": ["lump sum or phase in?"],
        "evidence": [{"as_of": "2026-10-06", "metric": "CAPE", "value": 40.6, "source": "web"}],
        "review": {"next_review": "2027-10-06", "triggers": ["drift > 5pp"]},
    }
    data.update(overrides)
    return data


def test_vocabulary_matches_backtest_and_sub_class_keys():
    for key in (
        "equity",
        "small_cap_value",
        "long_gilts",
        "intermediate_gilts",
        "short_gilts",
        "index_linked",
        "corporate_bonds",
        "gold",
        "commodities",
        "cash",
    ):
        assert key in PLAN_CLASSES


def test_valid_plan_parses_and_normalises():
    plan = parse_plan(plan_data(), "alex")
    assert plan.target_weights()["equity"] == 40
    assert plan.parent_weights() == {"equity": 40, "bond": 40, "commodity": 20}
    assert plan.vehicles["long_gilts"][0].ticker == "GLTL.L"
    assert plan.review.next_review.isoformat() == "2027-10-06"
    out = plan.to_dict()
    assert out["target"][0] == {"class": "equity", "weight_pct": 40.0}
    assert out["disclaimer"].endswith("not regulated advice.")


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"target": [{"class": "equity", "weight_pct": 60}, {"class": "gold", "weight_pct": 30}]}, "sum to 100%"),
        ({"target": [{"class": "crypto", "weight_pct": 100}]}, "Unknown class 'crypto'"),
        (
            {"target": [{"class": "gold", "weight_pct": 50}, {"class": "Gold", "weight_pct": 50}]},
            "more than once",
        ),
        ({"target": []}, "at least one class"),
        ({"updated": "06/10/2026"}, "date"),
        ({"vehicles": {"bitcoin": ["BTC"]}}, "Unknown vehicle class"),
        ({"vehicles": {"gold": [{}]}}, "ticker or a note"),
        ({"status": "final"}, "status"),
    ],
)
def test_invalid_plans_rejected(overrides, message):
    with pytest.raises(ValidationError) as excinfo:
        parse_plan(plan_data(**overrides), "alex")
    assert message in str(excinfo.value)


def test_weight_sum_tolerance():
    target = [{"class": "equity", "weight_pct": 33.333}, {"class": "gold", "weight_pct": 66.667}]
    assert parse_plan(plan_data(target=target), "alex")


def test_owner_mismatch_rejected():
    with pytest.raises(ValueError, match="does not match"):
        parse_plan(plan_data(owner="bob"), "alex")


def test_save_and_load_round_trip(tmp_path):
    plan = parse_plan(plan_data(), "alex")
    path = save_plan(plan, tmp_path)
    assert path == tmp_path / "plans" / "alex.json"
    assert json.loads(path.read_text(encoding="utf-8"))["owner"] == "alex"
    assert load_plan("alex", tmp_path) == plan
    assert not list((tmp_path / "plans").glob("*.tmp"))


def test_load_missing_plan(tmp_path):
    with pytest.raises(PlanNotFoundError, match="No investment plan saved for alex"):
        load_plan("alex", tmp_path)


@pytest.mark.parametrize("owner", ["../alex", "a/b", "", ".hidden"])
def test_owner_ids_cannot_escape_plans_dir(tmp_path, owner):
    with pytest.raises(ValueError):
        load_plan(owner, tmp_path)


def test_plans_dir_defaults_to_config_data_root(monkeypatch, tmp_path):
    monkeypatch.setattr(plan_mod.config, "data_root", tmp_path, raising=False)
    assert plan_mod.plans_dir() == tmp_path / "plans"


def test_vehicle_warnings_flag_unknown_tickers(monkeypatch):
    known = {"GLTL.L"}
    monkeypatch.setattr(plan_mod, "get_instrument_meta", lambda t: {"ticker": t} if t in known else {})
    data = plan_data(vehicles={"long_gilts": ["GLTL.L"], "gold": ["NOPE.L"], "equity": [{"note": "tbc"}]})
    assert vehicle_warnings(parse_plan(data, "alex")) == ["NOPE.L (gold) has no instrument metadata"]


def test_compare_rolls_up_when_policy_lacks_sub_classes(monkeypatch):
    # Pin the pre-#9543 behaviour: the policy only knows top-level classes.
    real = plan_mod.parse_policy

    def top_level_only(data):
        if not set(data["targets"]) <= {"equity", "bond", "commodity", "cash"}:
            raise ValueError("Unknown asset class")
        return real(data)

    monkeypatch.setattr(plan_mod, "parse_policy", top_level_only)
    plan = parse_plan(plan_data(), "alex")

    result = compare_with_rebalance_targets(plan, AllocationPolicy({"equity": 40, "bond": 40, "commodity": 20}, 3))
    assert result["copy_supported"] is False
    assert result["matches"] is True
    assert result["plan_targets"] == {"equity": 40, "bond": 40, "commodity": 20}
    assert result["tolerance_pct"] == 3

    assert compare_with_rebalance_targets(plan, AllocationPolicy({"equity": 60, "bond": 40}))["matches"] is False


def test_compare_copies_exact_keys_when_policy_accepts_them(monkeypatch):
    monkeypatch.setattr(plan_mod, "parse_policy", lambda data: type("P", (), {"targets": dict(data["targets"])})())
    plan = parse_plan(plan_data(), "alex")
    result = compare_with_rebalance_targets(plan, AllocationPolicy())
    assert result["copy_supported"] is True
    assert result["matches"] is False
    assert result["plan_targets"]["long_gilts"] == 10


def test_bare_string_vehicle_shorthand():
    plan = parse_plan(plan_data(vehicles={"gold": "PHGP.L", "equity": {"note": "tbc"}}), "alex")
    assert plan.vehicles["gold"][0].ticker == "PHGP.L"
    assert plan.vehicles["equity"][0].note == "tbc"


def test_compare_surfaces_errors_other_than_unknown_class(monkeypatch):
    def broken(data):
        raise ValueError("tolerance_pct must be a number")

    monkeypatch.setattr(plan_mod, "parse_policy", broken)
    with pytest.raises(ValueError, match="tolerance_pct"):
        compare_with_rebalance_targets(parse_plan(plan_data(), "alex"), AllocationPolicy())
