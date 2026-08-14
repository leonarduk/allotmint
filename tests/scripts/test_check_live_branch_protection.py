"""Unit tests for scripts/check_live_branch_protection.py.

The script's whole job is to notice when GitHub enforces something other than
`.github/rulesets/default-branch-protection.json`, so every test here builds a
live payload that differs from the checked-in one in exactly one way and
asserts the difference is reported. Issue #5728 existed because the previous
checker could not see any of this.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_live_branch_protection.py"
_spec = importlib.util.spec_from_file_location("check_live_branch_protection", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

REPO = "leonarduk/allotmint"
RULESET_ID = 7292508


def _checked_in() -> dict[str, Any]:
    return json.loads(_mod.RULESET_PATH.read_text(encoding="utf-8"))


def _live_from_checked_in() -> dict[str, Any]:
    """A live ruleset payload that agrees with the checked-in file."""
    live = copy.deepcopy(_checked_in())
    live["id"] = RULESET_ID
    return live


def _fetch_factory(
    *,
    ruleset: dict[str, Any] | None = None,
    rulesets_list: list[dict[str, Any]] | None = None,
    classic_contexts: list[str] | None = None,
    disabled_workflows: list[str] | None = None,
):
    """Build a `fetch` stub covering every endpoint the script calls."""
    live = _live_from_checked_in() if ruleset is None else ruleset
    listing = [{"id": RULESET_ID, "name": live.get("name")}] if rulesets_list is None else rulesets_list
    default_names = sorted(_mod.DISABLED_WORKFLOW_FILES)
    names = default_names if disabled_workflows is None else disabled_workflows
    workflows = [{"path": f".github/workflows/{name}", "state": "disabled_manually"} for name in names]

    def fetch(path: str) -> Any:
        if path == f"repos/{REPO}/rulesets":
            return listing
        if path == f"repos/{REPO}/rulesets/{RULESET_ID}":
            return live
        if path == f"repos/{REPO}/branches/main/protection":
            if classic_contexts is None:
                return None
            return {"required_status_checks": {"contexts": classic_contexts}}
        if path.startswith(f"repos/{REPO}/actions/workflows"):
            return {"workflows": workflows}
        raise AssertionError(f"unexpected API path: {path}")

    return fetch


def _errors(**kwargs) -> list[str]:
    exit_code, errors = _mod.run(_fetch_factory(**kwargs), REPO)
    assert (exit_code == _mod.EXIT_OK) == (not errors)
    return errors


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_no_drift_when_live_matches_checked_in() -> None:
    assert _errors() == []


# ---------------------------------------------------------------------------
# Ruleset-level drift
# ---------------------------------------------------------------------------


def test_missing_ruleset_is_drift() -> None:
    errors = _errors(rulesets_list=[{"id": 1, "name": "something else"}])
    assert any("no live ruleset named" in e for e in errors)


def test_inactive_enforcement_is_drift() -> None:
    live = _live_from_checked_in()
    live["enforcement"] = "evaluate"
    assert any("enforcement" in e for e in _errors(ruleset=live))


def test_ruleset_targeting_no_branches_is_drift() -> None:
    """The exact live state found in #5728: `include` was empty."""
    live = _live_from_checked_in()
    live["conditions"]["ref_name"]["include"] = []
    errors = _errors(ruleset=live)
    assert any("conditions.ref_name.include" in e for e in errors)


def test_missing_required_status_checks_rule_is_drift() -> None:
    """Also #5728: the live ruleset had no required_status_checks rule at all."""
    live = _live_from_checked_in()
    live["rules"] = [r for r in live["rules"] if r["type"] != "required_status_checks"]
    errors = _errors(ruleset=live)
    assert any("missing rule types" in e for e in errors)
    assert any("does not require checked-in contexts" in e for e in errors)


def test_extra_live_rule_type_is_drift() -> None:
    live = _live_from_checked_in()
    live["rules"].append({"type": "required_linear_history"})
    assert any("not checked in" in e for e in _errors(ruleset=live))


def test_review_policy_drift_is_reported() -> None:
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"]["required_approving_review_count"] = 2
    errors = _errors(ruleset=live)
    assert any("pull_request.required_approving_review_count" in e for e in errors)


def test_pull_request_parameters_absent_from_live_are_ignored() -> None:
    """GitHub may omit parameters; only shared keys are compared."""
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"].pop("require_last_push_approval")
    assert _errors(ruleset=live) == []


def test_allowed_merge_methods_compared_order_insensitively() -> None:
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "pull_request":
            rule["parameters"]["allowed_merge_methods"] = ["squash", "rebase", "merge"]
    assert _errors(ruleset=live) == []


# ---------------------------------------------------------------------------
# Required-context drift -- the failure mode that blocks every PR
# ---------------------------------------------------------------------------


def test_wrong_context_naming_convention_is_drift() -> None:
    """`CI / test` instead of `test` is the trap #5728 warns about."""
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            for check in rule["parameters"]["required_status_checks"]:
                if check["context"] == "test":
                    check["context"] = "CI / test"
    errors = _errors(ruleset=live)
    assert any("does not require checked-in contexts" in e and "'test'" in e for e in errors)
    assert any("not checked in" in e and "CI / test" in e for e in errors)


def test_integration_id_mismatch_is_drift() -> None:
    """A context whose producing App changes without the string changing."""
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            for check in rule["parameters"]["required_status_checks"]:
                if check["context"] == "test":
                    check["integration_id"] = 99999
    errors = _errors(ruleset=live)
    assert any("integration_id" in e and "'test'" in e for e in errors)


def test_integration_id_absent_from_checked_in_is_not_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checked-in entries with no integration_id opt out of this comparison."""
    expected = _checked_in()
    for rule in expected["rules"]:
        if rule["type"] == "required_status_checks":
            for check in rule["parameters"]["required_status_checks"]:
                check.pop("integration_id", None)
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            for check in rule["parameters"]["required_status_checks"]:
                check["integration_id"] = 1

    monkeypatch.setattr(_mod, "load_checked_in_ruleset", lambda: expected)
    _, errors = _mod.run(_fetch_factory(ruleset=live), REPO)
    assert not any("integration_id" in e for e in errors)


def test_dropped_context_is_drift() -> None:
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            rule["parameters"]["required_status_checks"] = [
                c for c in rule["parameters"]["required_status_checks"] if c["context"] != "test"
            ]
    assert any("does not require checked-in contexts" in e for e in _errors(ruleset=live))


def test_strict_policy_drift_is_reported() -> None:
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            rule["parameters"]["strict_required_status_checks_policy"] = False
    assert any("strict_required_status_checks_policy" in e for e in _errors(ruleset=live))


# ---------------------------------------------------------------------------
# The other two live mechanisms
# ---------------------------------------------------------------------------


def test_classic_protection_with_required_checks_is_drift() -> None:
    errors = _errors(classic_contexts=["test", "integration-tests"])
    assert any("classic branch protection also requires status checks" in e for e in errors)


def test_classic_protection_without_required_checks_is_fine() -> None:
    assert _errors(classic_contexts=[]) == []


def test_required_context_from_newly_disabled_workflow_is_drift() -> None:
    """Disabling `conflict-check.yml` in the UI must be caught immediately."""
    disabled = sorted(_mod.DISABLED_WORKFLOW_FILES | {"conflict-check.yml"})
    errors = _errors(disabled_workflows=disabled)
    assert any("not listed in DISABLED_WORKFLOW_FILES" in e for e in errors)
    assert any("can never report" in e and "Check for merge conflicts with main" in e for e in errors)


def test_context_matching_no_workflow_is_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    live = _live_from_checked_in()
    for rule in live["rules"]:
        if rule["type"] == "required_status_checks":
            rule["parameters"]["required_status_checks"].append({"context": "does-not-exist"})
    monkeypatch.setattr(_mod, "load_checked_in_ruleset", lambda: live)
    _, errors = _mod.run(_fetch_factory(ruleset=live), REPO)
    assert any("match no workflow job" in e for e in errors)


# ---------------------------------------------------------------------------
# API availability
# ---------------------------------------------------------------------------


def test_unavailable_api_exits_two_rather_than_reporting_no_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A permission failure must never be mistaken for a clean result.

    Exit 2 is distinct from exit 1 so the scheduled workflow's failure message
    distinguishes "the token expired" from "someone changed the gate".
    """

    def fetch(_path: str) -> Any:
        raise _mod.ApiUnavailable("token lacks Administration: read")

    monkeypatch.setattr(_mod, "gh_api", fetch)
    assert _mod.main(["--repo", REPO]) == _mod.EXIT_UNAVAILABLE


def test_clean_run_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_mod, "gh_api", _fetch_factory())
    assert _mod.main(["--repo", REPO]) == _mod.EXIT_OK
