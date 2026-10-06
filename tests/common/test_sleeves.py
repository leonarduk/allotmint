"""Sleeve store and per-sleeve plan (#9813)."""

from __future__ import annotations

import json

import pytest

from backend.common.allocation_policy import AllocationPolicy
from backend.common.rebalance_plan import build_plan
from backend.common.settings_file import SettingsUnreadableError
from backend.common.sleeve_plan import build_sleeved_plan, size_band, sleeve_new_cash, split_portfolio
from backend.common.sleeves import (
    CORE_ID,
    CoreSleeveError,
    SleeveNotFoundError,
    SleeveSetup,
    apply_strategy_to_sleeve,
    assign_ticker,
    create_sleeve,
    delete_sleeve,
    load_sleeves,
    update_sleeve,
)
from backend.common.strategies import StrategyNotFoundError

SPEC = {"equity": 70.0, "commodity": 30.0}


@pytest.fixture()
def root(tmp_path):
    (tmp_path / "alex").mkdir()
    (tmp_path / "bob").mkdir()
    return tmp_path


def _settings(root, owner="alex"):
    return json.loads((root / owner / "settings.json").read_text())


def _spec(root, size=10.0, **extra):
    return create_sleeve("alex", {"name": "Speculative", "size_pct": size, "targets": SPEC, **extra}, root)


def test_no_sleeves_by_default(root):
    setup = load_sleeves("alex", root)
    assert setup.sleeves == [] and setup.assignments == {}
    assert setup.core_size_pct == 100.0


def test_create_sleeve_keeps_other_settings(root):
    (root / "alex" / "settings.json").write_text(json.dumps({"allocation_policy": {"targets": {"equity": 100}}}))
    sleeve = _spec(root)
    assert sleeve.id.startswith("sleeve-")
    data = _settings(root)
    assert data["allocation_policy"] == {"targets": {"equity": 100}}
    assert data["sleeves"][0]["targets"] == SPEC
    assert load_sleeves("alex", root).core_size_pct == 90.0


def test_create_from_strategy_records_it(root):
    sleeve = create_sleeve("alex", {"name": "Spec", "size_pct": 10, "strategy_id": "barbell"}, root)
    assert sleeve.strategy["id"] == "barbell"
    assert sleeve.targets == {"cash": 45.0, "short_gilts": 45.0, "equity": 10.0}


@pytest.mark.parametrize(
    "body, message",
    [
        ({"name": "", "size_pct": 10, "targets": SPEC}, "name is required"),
        ({"name": "Core", "size_pct": 10, "targets": SPEC}, "reserved"),
        ({"name": "S", "size_pct": 0, "targets": SPEC}, "above 0%"),
        ({"name": "S", "size_pct": 100, "targets": SPEC}, "below 100%"),
        ({"name": "S", "size_pct": 10, "targets": {"equity": 60}}, "100%"),
    ],
)
def test_create_rejects_invalid(root, body, message):
    with pytest.raises(ValueError, match=message):
        create_sleeve("alex", body, root)


def test_sizes_must_leave_room_for_core(root):
    _spec(root, size=60)
    with pytest.raises(ValueError, match="leave some"):
        create_sleeve("alex", {"name": "Other", "size_pct": 40, "targets": SPEC}, root)
    assert len(load_sleeves("alex", root).sleeves) == 1


def test_duplicate_names_rejected(root):
    _spec(root)
    with pytest.raises(ValueError, match="already exists"):
        _spec(root, size=5)


def test_create_unknown_strategy(root):
    with pytest.raises(StrategyNotFoundError):
        create_sleeve("alex", {"name": "S", "size_pct": 10, "strategy_id": "nope"}, root)


def test_update_and_targets_clear_strategy(root):
    sleeve = create_sleeve("alex", {"name": "Spec", "size_pct": 10, "strategy_id": "100_equity"}, root)
    resized = update_sleeve("alex", sleeve.id, {"size_pct": 15}, root)
    assert resized.size_pct == 15.0 and resized.strategy["id"] == "100_equity"
    retargeted = update_sleeve("alex", sleeve.id, {"targets": SPEC}, root)
    assert retargeted.targets == SPEC and retargeted.strategy is None


def test_apply_strategy_to_sleeve(root):
    sleeve = _spec(root)
    applied = apply_strategy_to_sleeve("alex", sleeve.id, "permanent", root)
    assert applied.targets["gold"] == 25.0
    assert applied.strategy["name"] == "Permanent Portfolio"
    assert load_sleeves("alex", root).sleeves[0].strategy["id"] == "permanent"


def test_core_cannot_be_edited_here(root):
    with pytest.raises(CoreSleeveError):
        update_sleeve("alex", CORE_ID, {"size_pct": 5}, root)
    with pytest.raises(CoreSleeveError):
        delete_sleeve("alex", CORE_ID, root)
    with pytest.raises(SleeveNotFoundError):
        delete_sleeve("alex", "sleeve-missing", root)


def test_assignments_round_trip_and_are_owner_scoped(root):
    sleeve = _spec(root)
    assign_ticker("alex", " moon.l ", sleeve.id, root)
    setup = load_sleeves("alex", root)
    assert setup.assignments == {"MOON.L": sleeve.id}
    assert setup.sleeve_of("moon.l") == sleeve.id
    assert setup.sleeve_of("VWRL.L") == CORE_ID
    assert load_sleeves("bob", root).assignments == {}
    assign_ticker("alex", "MOON.L", CORE_ID, root)
    assert load_sleeves("alex", root).assignments == {}


def test_assign_to_unknown_sleeve(root):
    with pytest.raises(SleeveNotFoundError):
        assign_ticker("alex", "MOON.L", "sleeve-missing", root)


def test_delete_returns_holdings_to_core(root):
    sleeve = _spec(root)
    assign_ticker("alex", "MOON.L", sleeve.id, root)
    delete_sleeve("alex", sleeve.id, root)
    setup = load_sleeves("alex", root)
    assert setup.sleeves == [] and setup.assignments == {}


def test_unreadable_settings(root):
    (root / "alex" / "settings.json").write_text("{bad")
    assert load_sleeves("alex", root).sleeves == []
    with pytest.raises(SettingsUnreadableError):
        _spec(root)
    assert (root / "alex" / "settings.json").read_text() == "{bad"


def test_invalid_stored_sleeve_is_skipped(root):
    (root / "alex" / "settings.json").write_text(
        json.dumps({"sleeves": [{"id": "sleeve-x", "name": "X", "size_pct": 10, "targets": {"equity": 50}}]})
    )
    setup = load_sleeves("alex", root)
    assert setup.sleeves == []
    assert setup.warnings == [
        "A saved sleeve was ignored because it is invalid: Target weights must total 100%, got 50.00%"
    ]


def test_oversized_stored_sleeves_are_dropped_with_a_warning(root):
    big = {"name": "A", "size_pct": 60, "targets": {"equity": 100}}
    (root / "alex" / "settings.json").write_text(
        json.dumps({"sleeves": [{**big, "id": "sleeve-a"}, {**big, "id": "sleeve-b", "name": "B"}]})
    )
    setup = load_sleeves("alex", root)
    assert setup.sleeves == []
    assert len(setup.warnings) == 1 and "everything counts as core" in setup.warnings[0]


# ------------------------------------------------------------------ plans


def _portfolio():
    return {
        "accounts": [
            {
                "account_type": "SIPP",
                "_account_stem": "sipp",
                "holdings": [
                    {"ticker": "CASH.GBP", "market_value_gbp": 100.0, "instrument_type": "Cash"},
                    {"ticker": "CORE.L", "market_value_gbp": 800.0, "asset_class": "equity"},
                    {"ticker": "MOON.L", "market_value_gbp": 140.0, "asset_class": "equity"},
                    {"ticker": "OIL.L", "market_value_gbp": 60.0, "asset_class": "commodity"},
                ],
            }
        ]
    }


def _setup(root):
    sleeve = _spec(root)
    assign_ticker("alex", "MOON.L", sleeve.id, root)
    assign_ticker("alex", "OIL.L", sleeve.id, root)
    return load_sleeves("alex", root), sleeve


def test_without_sleeves_plan_is_unchanged():
    policy = AllocationPolicy(targets={"equity": 80.0, "cash": 20.0})
    assert build_sleeved_plan(_portfolio(), policy, SleeveSetup()) == build_plan(_portfolio(), policy)


def test_split_portfolio_keeps_accounts(root):
    setup, sleeve = _setup(root)
    parts = split_portfolio(_portfolio(), setup)
    assert [h["ticker"] for h in parts[CORE_ID]["accounts"][0]["holdings"]] == ["CASH.GBP", "CORE.L"]
    assert [h["ticker"] for h in parts[sleeve.id]["accounts"][0]["holdings"]] == ["MOON.L", "OIL.L"]
    assert parts[sleeve.id]["accounts"][0]["_account_stem"] == "sipp"


def test_sleeved_plan_separates_core_and_speculative(root):
    setup, sleeve = _setup(root)
    policy = AllocationPolicy(targets={"equity": 80.0, "cash": 20.0}, tolerance_pct=5.0)
    plan = build_sleeved_plan(_portfolio(), policy, setup, {"id": "x", "name": "X"})

    # Core drift ignores the speculative holdings: 800 equity of a 900 core.
    assert plan["total_value"] == 900.0
    assert plan["portfolio_total"] == 1100.0
    equity = next(r for r in plan["classes"] if r["asset_class"] == "equity")
    assert equity["current_value"] == 800.0

    core_row, spec_row = plan["sleeves"]
    assert core_row["id"] == CORE_ID and core_row["size_target_pct"] == 90.0
    assert core_row["strategy"] == {"id": "x", "name": "X"}
    assert "plan" not in core_row
    assert spec_row["id"] == sleeve.id
    assert spec_row["size_current_pct"] == pytest.approx(18.18, abs=0.01)
    assert spec_row["size_drift_pct"] == pytest.approx(8.18, abs=0.01)
    assert spec_row["in_band"] is False
    spec_classes = {r["asset_class"]: r for r in spec_row["plan"]["classes"]}
    assert spec_classes["equity"]["current_pct"] == 70.0
    assert spec_classes["commodity"]["target_pct"] == 30.0
    assert any("Speculative sleeve is 18.18%" in n for n in plan["notes"])


def test_sleeve_new_cash_targets_that_sleeve(root):
    setup, sleeve = _setup(root)
    policy = AllocationPolicy(targets={"equity": 80.0, "cash": 20.0})
    result = sleeve_new_cash(_portfolio(), policy, setup, sleeve.id, 100.0, "sipp")
    # Speculative is at 70/30 already, so new money splits 70/30 too.
    assert {t["asset_class"]: t["amount"] for t in result["trades"]} == {"equity": 70.0, "commodity": 30.0}
    with pytest.raises(ValueError, match="Unknown sleeve"):
        sleeve_new_cash(_portfolio(), policy, setup, "sleeve-missing", 100.0, "sipp")


def test_sleeve_sizes_cover_the_whole_portfolio(root):
    """Cash and unclassified holdings count towards their sleeve, so current sizes add up to 100%."""
    sleeve = _spec(root)
    assign_ticker("alex", "MOON.L", sleeve.id, root)
    assign_ticker("alex", "ODD.L", sleeve.id, root)
    portfolio = _portfolio()
    portfolio["accounts"][0]["holdings"].append({"ticker": "ODD.L", "market_value_gbp": 50.0})
    plan = build_sleeved_plan(portfolio, AllocationPolicy(targets={"equity": 100.0}), load_sleeves("alex", root))
    assert plan["portfolio_total"] == 1150.0
    assert sum(row["size_current_pct"] for row in plan["sleeves"]) == pytest.approx(100.0, abs=0.02)
    assert sum(row["current_value"] for row in plan["sleeves"]) == pytest.approx(1150.0)


@pytest.mark.parametrize(
    "target, tolerance, band",
    [(10.0, 5.0, 2.5), (90.0, 5.0, 5.0), (2.0, 5.0, 0.5), (40.0, 3.0, 3.0)],
)
def test_size_band_is_the_smaller_of_absolute_and_relative(target, tolerance, band):
    assert size_band(target, tolerance) == band


def test_speculative_sleeve_at_14_against_10_is_flagged(root):
    """The issue's own example: 4pp over a 10% target is out of band at a 5pp class tolerance."""
    setup, sleeve = _setup(root)
    portfolio = {
        "accounts": [
            {
                "account_type": "SIPP",
                "_account_stem": "sipp",
                "holdings": [
                    {"ticker": "CORE.L", "market_value_gbp": 860.0, "asset_class": "equity"},
                    {"ticker": "MOON.L", "market_value_gbp": 140.0, "asset_class": "equity"},
                ],
            }
        ]
    }
    plan = build_sleeved_plan(portfolio, AllocationPolicy(targets={"equity": 100.0}, tolerance_pct=5.0), setup)
    core_row, spec_row = plan["sleeves"]
    assert spec_row["size_current_pct"] == 14.0 and spec_row["size_band_pct"] == 2.5
    assert spec_row["in_band"] is False
    # The core is 86% against 90%: inside its 5pp band.
    assert core_row["in_band"] is True
    assert any("Speculative sleeve is 14.00%" in n and "2.5pp" in n for n in plan["notes"])


def test_new_cash_into_a_sleeve_the_account_holds_nothing_in(root):
    setup, sleeve = _setup(root)
    portfolio = _portfolio()
    portfolio["accounts"].append({"account_type": "ISA", "_account_stem": "isa", "holdings": []})
    result = sleeve_new_cash(portfolio, AllocationPolicy(targets={"equity": 100.0}), setup, sleeve.id, 100.0, "isa")
    assert result["account_id"] == "isa"
    assert {t["asset_class"]: t["amount"] for t in result["trades"]} == {"equity": 70.0, "commodity": 30.0}
    assert all(t["ticker"] is None for t in result["trades"])
