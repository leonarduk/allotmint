"""Model, validation and storage of the per-owner investment plan (#9547)."""

from __future__ import annotations

import json
from datetime import date

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
    plan_weights_from_rebalance,
    rebalance_weights,
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


def test_owner_with_space_round_trips(tmp_path):
    plan = parse_plan(plan_data(owner="mary jane"), "mary jane")
    assert save_plan(plan, tmp_path) == tmp_path / "plans" / "mary jane.json"
    assert load_plan("mary jane", tmp_path) == plan


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


def small_value_plan():
    return parse_plan(
        plan_data(
            target=[
                {"class": "equity", "weight_pct": 30},
                {"class": "small_cap_value", "weight_pct": 10},
                {"class": "long_gilts", "weight_pct": 25},
                {"class": "index_linked", "weight_pct": 15},
                {"class": "gold", "weight_pct": 20},
            ]
        ),
        "alex",
    )


def test_rebalance_weights_keeps_the_equity_split_as_broad_equity():
    # small_cap_value is a policy sub-class (#9653), so equity beside it is broad_equity.
    assert rebalance_weights(small_value_plan()) == {
        "broad_equity": 30,
        "small_cap_value": 10,
        "long_gilts": 25,
        "index_linked": 15,
        "gold": 20,
    }


def test_compare_keeps_sub_class_split_when_plan_has_small_cap_value():
    result = compare_with_rebalance_targets(small_value_plan(), AllocationPolicy({"equity": 60, "bond": 40}))
    assert result["copy_supported"] is True
    assert result["matches"] is False
    assert result["plan_targets"] == {
        "broad_equity": 30,
        "small_cap_value": 10,
        "long_gilts": 25,
        "index_linked": 15,
        "gold": 20,
    }

    copied = AllocationPolicy(result["plan_targets"])
    assert compare_with_rebalance_targets(small_value_plan(), copied)["matches"] is True


def test_bare_string_vehicle_shorthand():
    plan = parse_plan(plan_data(vehicles={" Gold": "PHGP.L", "equity": {"note": "tbc"}}), "alex")
    assert plan.vehicles["gold"][0].ticker == "PHGP.L"
    assert plan.vehicles["equity"][0].note == "tbc"


def test_compare_surfaces_errors_other_than_unknown_class(monkeypatch):
    def broken(data):
        raise ValueError("tolerance_pct must be a number")

    monkeypatch.setattr(plan_mod, "parse_policy", broken)
    with pytest.raises(ValueError, match="tolerance_pct"):
        compare_with_rebalance_targets(parse_plan(plan_data(), "alex"), AllocationPolicy())


def test_compare_rolls_up_on_a_level_clash(monkeypatch):
    real = plan_mod.parse_policy
    calls = []

    def clash_once(data):
        calls.append(data)
        if len(calls) == 1:
            raise ValueError("Set Bond either as a whole or by sub-class, not both")
        return real(data)

    monkeypatch.setattr(plan_mod, "parse_policy", clash_once)
    result = compare_with_rebalance_targets(parse_plan(plan_data(), "alex"), AllocationPolicy())
    assert result["copy_supported"] is False
    assert result["plan_targets"] == {"equity": 40, "bond": 40, "commodity": 20}


def test_vocabulary_error_matches_the_real_policy_messages():
    for targets in ({"bond": 50, "long_gilts": 50}, {"mid_cap_growth": 100}):
        with pytest.raises(ValueError) as exc:
            plan_mod.parse_policy({"targets": targets})
        assert plan_mod._is_vocabulary_error(exc.value)


def test_vocabulary_error_rejects_a_longer_message_that_mentions_a_level_clash():
    compound = ValueError("Set Bond either as a whole or by sub-class, not both; targets must sum to 100%")
    assert not plan_mod._is_vocabulary_error(compound)


def test_compare_surfaces_other_errors_starting_with_set(monkeypatch):
    def broken(data):
        raise ValueError("Set targets must sum to 100%")

    monkeypatch.setattr(plan_mod, "parse_policy", broken)
    with pytest.raises(ValueError, match="sum to 100"):
        compare_with_rebalance_targets(parse_plan(plan_data(), "alex"), AllocationPolicy())


PROFILE = {
    "risk_tolerance": {"level": "medium", "note": "can sit through a 20% fall"},
    "capacity_for_loss": {"level": "high"},
    "goals": [
        {"name": "Drawdown", "purpose": "retirement", "target_date": "2033-04-06", "priority": 1},
        {"name": "Joe university", "purpose": "education", "target_date": "2033-09-01", "amount_gbp": 30000},
        {"name": "Rainy day", "purpose": "general_wealth"},
    ],
}


def test_plan_without_profile_still_loads():
    plan = parse_plan(plan_data(), "alex")
    assert plan.profile is None
    assert "profile" not in plan.to_dict()


def test_profile_round_trips(tmp_path):
    plan = parse_plan(plan_data(profile=PROFILE), "alex")
    assert plan.profile.risk_tolerance.level == "medium"
    assert plan.profile.goals[1].target_date.isoformat() == "2033-09-01"
    out = plan.to_dict()["profile"]
    assert out["capacity_for_loss"] == {"level": "high"}
    assert out["goals"][2] == {"name": "Rainy day", "purpose": "general_wealth"}
    save_plan(plan, tmp_path)
    assert load_plan("alex", tmp_path) == plan


@pytest.mark.parametrize(
    "profile, message",
    [
        ({"risk_tolerance": {"level": "very high"}}, "risk_tolerance.level"),
        ({"goals": [{"name": "x", "purpose": "yacht"}]}, "purpose"),
        ({"goals": [{"name": "", "purpose": "other"}]}, "name"),
        ({"goals": [{"name": "  ", "purpose": "other"}]}, "name"),
        ({"goals": [{"name": "x", "purpose": "other", "amount_gbp": -1}]}, "amount_gbp"),
        ({"goals": [{"name": "x", "purpose": "other", "priority": 0}]}, "priority"),
        ({"suitability": "high"}, "suitability"),
    ],
)
def test_invalid_profile_rejected(profile, message):
    with pytest.raises(ValidationError) as excinfo:
        parse_plan(plan_data(profile=profile), "alex")
    assert message in str(excinfo.value)


def test_profile_horizon_derives_age_and_years_to_goal():
    plan = parse_plan(plan_data(profile=PROFILE), "alex")
    horizon = plan_mod.profile_horizon(plan, "1975-10-07", today=date(2026, 10, 6))
    assert horizon["age"] == 50  # birthday is tomorrow
    assert horizon["goals"] == [
        {"index": 0, "name": "Drawdown", "years_to_goal": 6.5},
        {"index": 1, "name": "Joe university", "years_to_goal": 6.9},
    ]


def test_profile_horizon_without_dob_or_profile():
    plan = parse_plan(plan_data(), "alex")
    assert plan_mod.profile_horizon(plan, None) == {"age": None, "goals": []}
    assert plan_mod.profile_horizon(plan, "not-a-date")["age"] is None


def test_profile_horizon_goal_in_the_past_is_negative():
    plan = parse_plan(
        plan_data(profile={"goals": [{"name": "x", "purpose": "other", "target_date": "2025-10-06"}]}), "alex"
    )
    assert plan_mod.profile_horizon(plan, None, today=date(2026, 10, 6))["goals"][0]["years_to_goal"] == -1.0


def test_profile_horizon_index_skips_undated_goals():
    goals = [
        {"name": "a", "purpose": "other", "target_date": "2027-10-06"},
        {"name": "b", "purpose": "other"},
        {"name": "c", "purpose": "other", "target_date": "2028-10-06"},
    ]
    plan = parse_plan(plan_data(profile={"goals": goals}), "alex")
    horizon = plan_mod.profile_horizon(plan, None, today=date(2026, 10, 6))
    assert [(g["index"], g["name"]) for g in horizon["goals"]] == [(0, "a"), (2, "c")]


def test_plan_weights_from_rebalance_maps_strategy_keys_to_plan_classes():
    # All Weather as the Strategy page applies it.
    targets = {"equity": 30, "long_gilts": 40, "intermediate_gilts": 15, "gold": 7.5, "commodities": 7.5}
    assert plan_weights_from_rebalance(targets) == {
        "equity": 30,
        "long_gilts": 40,
        "intermediate_gilts": 15,
        "gold": 7.5,
        "commodities": 7.5,
    }
    assert plan_weights_from_rebalance({"equity": 70, "commodity": 30}) == {"equity": 70, "commodities": 30}
    assert plan_weights_from_rebalance({"broad_equity": 20, "small_cap_value": 80}) == {
        "equity": 20,
        "small_cap_value": 80,
    }


@pytest.mark.parametrize(
    "targets",
    [{"equity": 60, "bond": 40}, {"equity": 90, "property": 10}, {}, {"equity": 50}],
)
def test_plan_weights_from_rebalance_none_when_unmappable(targets):
    assert plan_weights_from_rebalance(targets) is None


def test_compare_offers_rebalance_targets_as_plan_target():
    plan = parse_plan(plan_data(), "alex")
    result = compare_with_rebalance_targets(plan, AllocationPolicy({"equity": 80, "intermediate_gilts": 20}))
    assert result["matches"] is False
    assert result["rebalance_as_plan"] == {"equity": 80, "intermediate_gilts": 20}
    # The mapped target is a valid plan target.
    rows = [{"class": k, "weight_pct": v} for k, v in result["rebalance_as_plan"].items()]
    assert parse_plan(plan_data(target=rows), "alex").target_weights() == result["rebalance_as_plan"]
