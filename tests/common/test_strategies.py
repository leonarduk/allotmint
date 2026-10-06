"""Strategy library: built-in definitions, user CRUD, apply and "modified" (#9653)."""

from __future__ import annotations

import json

import pytest

from backend.common.allocation_policy import AllocationPolicy, load_allocation_policy, save_allocation_policy
from backend.common.settings_file import SettingsUnreadableError
from backend.common.strategies import (
    BUILTIN_STRATEGIES,
    BuiltinStrategyError,
    StrategyNotFoundError,
    active_strategy,
    apply_strategy,
    create_strategy,
    delete_strategy,
    duplicate_strategy,
    get_strategy,
    list_strategies,
    load_user_strategies,
    matching_strategy,
    update_strategy,
    validate_targets,
)
from backend.common.sub_asset_class import policy_targets

# allotmint-pro backtest_portfolio PRESETS (allotmint_pro/mcp_server/backtest_tools.py) as fractions.
# cash_bucket_60_40 is omitted on purpose: its cash share depends on the withdrawal amount.
BACKTEST_PRESETS = {
    "60_40": {"equity": 0.60, "intermediate_gilts": 0.40},
    "80_20": {"equity": 0.80, "intermediate_gilts": 0.20},
    "permanent": {"equity": 0.25, "long_gilts": 0.25, "gold": 0.25, "cash": 0.25},
    "all_weather": {
        "equity": 0.30,
        "long_gilts": 0.40,
        "intermediate_gilts": 0.15,
        "gold": 0.075,
        "commodities": 0.075,
    },
    "golden_butterfly": {
        "equity": 0.20,
        "small_cap_value": 0.20,
        "long_gilts": 0.20,
        "short_gilts": 0.20,
        "gold": 0.20,
    },
}

GB_50_50 = {"equity": 40.0, "long_gilts": 10.0, "intermediate_gilts": 10.0, "short_gilts": 20.0, "gold": 20.0}


@pytest.fixture()
def root(tmp_path):
    (tmp_path / "alex").mkdir()
    return tmp_path


def _settings(root):
    return json.loads((root / "alex" / "settings.json").read_text())


@pytest.mark.parametrize("strategy", BUILTIN_STRATEGIES, ids=lambda s: s.id)
def test_every_builtin_validates_and_is_documented(strategy):
    assert validate_targets(strategy.targets) == strategy.targets
    assert strategy.builtin is True
    assert strategy.name and strategy.description and strategy.source and strategy.uk_mapping


def test_builtin_ids_are_unique():
    ids = [s.id for s in BUILTIN_STRATEGIES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("preset", sorted(BACKTEST_PRESETS))
def test_builtins_match_backtest_presets(preset):
    expected = policy_targets({k: v * 100 for k, v in BACKTEST_PRESETS[preset].items()})
    builtin = get_strategy("alex", preset)
    assert builtin.targets == pytest.approx(expected)


def test_golden_butterfly_50_50_variant():
    assert get_strategy("alex", "golden_butterfly_no_scv_50_50").targets == GB_50_50


def test_list_puts_builtins_first_and_flags_them(root):
    create_strategy("alex", {"name": "Mine", "targets": {"equity": 100}}, root)
    dicts = [s.to_dict() for s in list_strategies("alex", root)]
    assert dicts[0]["id"] == "60_40"
    assert [d["builtin"] for d in dicts] == [True] * len(BUILTIN_STRATEGIES) + [False]
    assert dicts[-1]["name"] == "Mine"


def test_create_update_delete_round_trip(root):
    (root / "alex" / "settings.json").write_text(json.dumps({"hold_days_min": 30}))
    created = create_strategy(
        "alex", {"name": " Mine ", "description": "d", "targets": {"Equities": 70, "bond": 30}}, root
    )
    assert created.id.startswith("user-")
    assert created.name == "Mine"
    assert created.targets == {"equity": 70.0, "bond": 30.0}

    updated = update_strategy("alex", created.id, {"name": "Renamed"}, root)
    assert updated.name == "Renamed"
    assert updated.targets == created.targets
    assert get_strategy("alex", created.id, root).name == "Renamed"

    delete_strategy("alex", created.id, root)
    assert load_user_strategies("alex", root) == []
    assert _settings(root)["hold_days_min"] == 30


@pytest.mark.parametrize(
    "body, match",
    [
        ({"name": "", "targets": {"equity": 100}}, "Name is required"),
        ({"name": "x" * 81, "targets": {"equity": 100}}, "at most 80"),
        ({"name": "Bad", "targets": {"equity": 60}}, "total 100"),
        ({"name": "Bad", "targets": {}}, "at least one target"),
        ({"name": "Bad", "targets": {"equity": 50, "broad_equity": 50}}, "either as a whole or by sub-class"),
        ({"name": "Bad", "targets": {"crypto": 100}}, "Unknown asset class"),
    ],
)
def test_create_rejects_invalid(root, body, match):
    with pytest.raises(ValueError, match=match):
        create_strategy("alex", body, root)
    assert not (root / "alex" / "settings.json").exists()


def test_builtins_cannot_be_edited_or_deleted(root):
    with pytest.raises(BuiltinStrategyError, match="duplicate"):
        update_strategy("alex", "permanent", {"name": "Mine"}, root)
    with pytest.raises(BuiltinStrategyError):
        delete_strategy("alex", "permanent", root)
    assert get_strategy("alex", "permanent", root).targets["gold"] == 25.0


def test_unknown_strategy_raises(root):
    with pytest.raises(StrategyNotFoundError):
        get_strategy("alex", "user-nope", root)
    with pytest.raises(StrategyNotFoundError):
        update_strategy("alex", "user-nope", {"name": "x"}, root)
    with pytest.raises(StrategyNotFoundError):
        delete_strategy("alex", "user-nope", root)


def test_duplicate_builtin_makes_an_editable_copy(root):
    copy = duplicate_strategy("alex", "golden_butterfly", accounts_root=root)
    assert copy.name == "Copy of Golden Butterfly"
    assert copy.targets == get_strategy("alex", "golden_butterfly").targets
    assert copy.extra["duplicated_from"] == "golden_butterfly"
    edited = update_strategy("alex", copy.id, {"targets": {"equity": 50, "gold": 50}}, root)
    assert edited.targets == {"equity": 50.0, "gold": 50.0}
    assert get_strategy("alex", "golden_butterfly").targets["gold"] == 20.0


def test_duplicate_user_strategy_with_name(root):
    original = create_strategy("alex", {"name": "Mine", "targets": {"equity": 100}}, root)
    copy = duplicate_strategy("alex", original.id, "Mine v2", root)
    assert copy.id != original.id
    assert [s.name for s in load_user_strategies("alex", root)] == ["Mine", "Mine v2"]


def test_apply_writes_policy_keeps_tolerance_and_records_active(root):
    save_allocation_policy("alex", AllocationPolicy({"equity": 100.0}, 3.0), root)
    policy = apply_strategy("alex", "golden_butterfly_no_scv_50_50", root)
    assert policy.targets == GB_50_50
    assert policy.tolerance_pct == 3.0
    assert load_allocation_policy("alex", root).targets == GB_50_50

    active = active_strategy("alex", root)
    assert active["id"] == "golden_butterfly_no_scv_50_50"
    assert active["name"] == "Golden Butterfly without small-value, 50/50 gilts"
    assert active["builtin"] is True
    assert active["modified"] is False
    assert active["applied_targets"] == GB_50_50


def test_apply_keeps_every_sub_class_target(root):
    policy = apply_strategy("alex", "golden_butterfly", root)
    assert set(policy.targets) == {"broad_equity", "small_cap_value", "long_gilts", "short_gilts", "gold"}
    assert sum(policy.targets.values()) == pytest.approx(100.0)


def test_editing_targets_after_apply_marks_modified(root):
    apply_strategy("alex", "60_40", root)
    save_allocation_policy("alex", AllocationPolicy({"equity": 70.0, "intermediate_gilts": 30.0}), root)
    assert active_strategy("alex", root)["modified"] is True
    save_allocation_policy("alex", AllocationPolicy({"equity": 60.0, "intermediate_gilts": 40.0}), root)
    assert active_strategy("alex", root)["modified"] is False


def test_active_reports_edited_and_deleted_user_strategy(root):
    mine = create_strategy("alex", {"name": "Mine", "targets": {"equity": 100}}, root)
    apply_strategy("alex", mine.id, root)
    update_strategy("alex", mine.id, {"targets": {"equity": 90, "gold": 10}}, root)
    active = active_strategy("alex", root)
    assert active["strategy_changed"] is True
    assert active["modified"] is False

    delete_strategy("alex", mine.id, root)
    active = active_strategy("alex", root)
    assert active["exists"] is False
    assert active["name"] == "Mine"


def test_no_active_strategy_for_an_existing_custom_policy(root):
    save_allocation_policy("alex", AllocationPolicy({"equity": 100.0}), root)
    assert active_strategy("alex", root) is None
    assert load_allocation_policy("alex", root).targets == {"equity": 100.0}


def test_invalid_stored_entries_are_skipped_but_kept(root):
    (root / "alex" / "settings.json").write_text(
        json.dumps({"strategies": [{"id": "user-bad", "name": "Bad", "targets": {"equity": 10}}, "junk"]})
    )
    assert load_user_strategies("alex", root) == []
    create_strategy("alex", {"name": "Good", "targets": {"equity": 100}}, root)
    stored = _settings(root)["strategies"]
    assert stored[0]["id"] == "user-bad"
    assert stored[1] == "junk"
    assert len(stored) == 3


def test_corrupt_settings_are_never_overwritten(root):
    path = root / "alex" / "settings.json"
    path.write_text("{not json")
    assert load_user_strategies("alex", root) == []
    with pytest.raises(SettingsUnreadableError):
        create_strategy("alex", {"name": "Mine", "targets": {"equity": 100}}, root)
    with pytest.raises(SettingsUnreadableError):
        apply_strategy("alex", "60_40", root)
    assert path.read_text() == "{not json"


def test_matching_strategy_finds_builtin_then_user(root):
    assert matching_strategy(GB_50_50, "alex", root).id == "golden_butterfly_no_scv_50_50"
    mine = create_strategy("alex", {"name": "Mine", "targets": {"equity": 55, "gold": 45}}, root)
    assert matching_strategy({"equity": 55, "gold": 45}, "alex", root).id == mine.id
    assert matching_strategy({"equity": 1, "gold": 99}, "alex", root) is None
    assert matching_strategy({}, "alex", root) is None
