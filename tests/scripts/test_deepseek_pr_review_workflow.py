"""Regression tests for the DeepSeek PR review workflow's label-based model selection.

The `Deep Review Required` label controls which DeepSeek model and token
budget a PR review run uses. That decision lives entirely in GitHub Actions
expression syntax in `deepseek-pr-review.yml` (not in Python), so it isn't
covered by the DeepSeek script's own unit tests in
`tests/test_ai_review_scripts.py`. These tests parse the workflow file's
actual expressions and evaluate them against simulated label sets and
events, so a regression in the conditional logic breaks a test here instead
of only surfacing in a live PR run.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deepseek-pr-review.yml"
)

REQUIRED_LABEL = "Deep Review Required"


def _ai_review_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow["jobs"]["ai-review"]


def _resolve_ternary(expr: str) -> tuple[str, str, str]:
    """Parse `contains(..., 'LABEL') && 'TRUE_VAL' || 'FALSE_VAL'` from a workflow expression."""
    match = re.search(
        r"contains\(github\.event\.pull_request\.labels\.\*\.name,\s*'([^']+)'\)"
        r"\s*&&\s*'([^']*)'\s*\|\|\s*'([^']*)'",
        expr,
    )
    assert match, f"Could not parse label-based ternary expression: {expr!r}"
    return match.group(1), match.group(2), match.group(3)


def _resolve_model_and_tokens(labels: list[str]) -> tuple[str, str]:
    job = _ai_review_job()

    label_name, true_model, false_model = _resolve_ternary(job["with"]["deepseek_model"])
    assert label_name == REQUIRED_LABEL
    model = true_model if label_name in labels else false_model

    label_name, true_tokens, false_tokens = _resolve_ternary(job["with"]["deepseek_max_tokens"])
    assert label_name == REQUIRED_LABEL
    tokens = true_tokens if label_name in labels else false_tokens

    return model, tokens


def test_deep_review_required_label_selects_reasoner_model_and_larger_token_budget() -> None:
    model, tokens = _resolve_model_and_tokens([REQUIRED_LABEL])

    assert model == "deepseek-reasoner"
    assert tokens == "16000"


def test_unrelated_labels_select_empty_overrides_so_script_defaults_apply() -> None:
    model, tokens = _resolve_model_and_tokens(["bug", "needs-triage"])

    assert model == ""
    assert tokens == ""


def test_no_labels_select_empty_overrides_so_script_defaults_apply() -> None:
    model, tokens = _resolve_model_and_tokens([])

    assert model == ""
    assert tokens == ""


def _job_runs(
    actor: str, action: str, enable_var: str | None = None, label_name: str | None = None
) -> bool:
    """Evaluate the ai-review job's `if:` condition for a simulated event."""
    condition = _ai_review_job()["if"]

    actor_match = re.search(r"github\.actor != '([^']+)'", condition)
    assert actor_match, f"Could not find actor gate in job condition: {condition!r}"
    blocked_actor = actor_match.group(1)

    disabled_match = re.search(r"vars\.ENABLE_DEEPSEEK_REVIEW != '([^']+)'", condition)
    assert (
        disabled_match
    ), f"Could not find ENABLE_DEEPSEEK_REVIEW gate in job condition: {condition!r}"
    disabled_value = disabled_match.group(1)

    required_label_match = re.search(r"github\.event\.label\.name == '([^']+)'", condition)
    assert required_label_match, f"Could not find label gate in job condition: {condition!r}"
    required_label = required_label_match.group(1)

    if actor == blocked_actor:
        return False
    if enable_var == disabled_value:
        return False
    if action in ("labeled", "unlabeled"):
        return label_name == required_label
    return True


def test_job_runs_on_synchronize_regardless_of_labels() -> None:
    assert _job_runs("alice", "synchronize") is True


def test_job_runs_when_deep_review_required_label_added() -> None:
    assert _job_runs("alice", "labeled", label_name=REQUIRED_LABEL) is True


def test_job_re_evaluates_when_deep_review_required_label_removed() -> None:
    assert _job_runs("alice", "unlabeled", label_name=REQUIRED_LABEL) is True


def test_job_skips_when_unrelated_label_added_or_removed() -> None:
    assert _job_runs("alice", "labeled", label_name="bug") is False
    assert _job_runs("alice", "unlabeled", label_name="bug") is False


def test_job_skips_for_dependabot() -> None:
    assert _job_runs("dependabot[bot]", "synchronize") is False


def test_job_skips_when_review_disabled_via_repo_var() -> None:
    assert _job_runs("alice", "synchronize", enable_var="false") is False
