"""Guard the invariants that make per-area CI gating safe.

Gating jobs on "did this PR touch my area?" trades wall-clock for a new
failure mode: a job that skips when it should have run reports as a *passing*
required check, so the PR merges green with the regression uncaught. These
tests pin the properties that make that impossible to introduce by accident.

See scripts/classify_change.py and .github/workflows/_classify-change.yml.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CLASSIFIER_WORKFLOW = WORKFLOWS / "_classify-change.yml"
CLASSIFIER_WORKFLOW_REF = "./.github/workflows/_classify-change.yml"

# Workflows that gate jobs on the shared classifier.
GATED_WORKFLOWS = (
    "ci.yml",
    "backend-integration.yml",
    "frontend-tests.yml",
    "iac-validation.yml",
)

_SCRIPT = REPO_ROOT / "scripts" / "classify_change.py"
_spec = importlib.util.spec_from_file_location("classify_change", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
AREAS: tuple[str, ...] = _mod.AREAS

_OUTPUT_REF = re.compile(r"needs\.classify-change\.outputs\.([A-Za-z0-9_-]+)")


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _gated_jobs(workflow: dict) -> list[tuple[str, str]]:
    """Return (job_id, if_expression) for jobs gated on a classifier output."""
    gated: list[tuple[str, str]] = []
    for job_id, job in workflow.get("jobs", {}).items():
        if not isinstance(job, dict):
            continue
        condition = job.get("if")
        if isinstance(condition, str) and "classify-change.outputs" in condition:
            gated.append((job_id, condition))
    return gated


ALL_GATED_JOBS = [
    pytest.param(name, job_id, condition, id=f"{name}:{job_id}")
    for name in GATED_WORKFLOWS
    for job_id, condition in _gated_jobs(_load(name))
]


def test_every_gated_workflow_actually_gates_something() -> None:
    """A workflow listed here but gating nothing means this file has gone stale."""
    for name in GATED_WORKFLOWS:
        assert _gated_jobs(_load(name)), f"{name} references no classify-change output"


@pytest.mark.parametrize(("workflow", "job_id", "condition"), ALL_GATED_JOBS)
def test_gates_use_fail_safe_polarity(workflow: str, job_id: str, condition: str) -> None:
    """`!= 'false'` runs the job when the classifier failed; `== 'true'` skips it.

    A failed classifier produces empty outputs. Under `== 'true'` the job then
    skips, GitHub reports the required check as passing, and the suite never
    ran -- the exact fail-open this design forbids.
    """
    assert "!= 'false'" in condition, (
        f"{workflow}:{job_id} must gate with \"<area> != 'false'\" so an empty "
        f"classifier output runs the job. Found: {condition!r}"
    )
    assert "== 'true'" not in condition, (
        f"{workflow}:{job_id} gates with \"== 'true'\", which silently skips the "
        f"job (and passes its required check) whenever the classifier fails. "
        f"Found: {condition!r}"
    )


@pytest.mark.parametrize(("workflow", "job_id", "condition"), ALL_GATED_JOBS)
def test_gates_survive_a_classifier_failure(workflow: str, job_id: str, condition: str) -> None:
    """Without `!cancelled()`, a failed `needs` skip-propagates to the gated job."""
    assert "!cancelled()" in condition, (
        f"{workflow}:{job_id} must include !cancelled() so a classify-change "
        f"failure doesn't skip-propagate into a silently-passing check. "
        f"Found: {condition!r}"
    )


@pytest.mark.parametrize(("workflow", "job_id", "condition"), ALL_GATED_JOBS)
def test_gates_reference_a_real_classifier_output(workflow: str, job_id: str, condition: str) -> None:
    """A typo'd area name yields an empty string, quietly disabling the gate."""
    valid = {*AREAS, "doc-only"}
    referenced = set(_OUTPUT_REF.findall(condition))
    assert referenced, f"{workflow}:{job_id} has no parseable classifier output reference"
    unknown = referenced - valid
    assert not unknown, (
        f"{workflow}:{job_id} references unknown classifier output(s) {sorted(unknown)}; "
        f"valid outputs are {sorted(valid)}"
    )


@pytest.mark.parametrize("workflow", GATED_WORKFLOWS)
def test_classification_comes_from_the_shared_reusable_workflow(workflow: str) -> None:
    """One classifier, not four competing detection mechanisms."""
    job = _load(workflow)["jobs"]["classify-change"]
    assert job.get("uses") == CLASSIFIER_WORKFLOW_REF, (
        f"{workflow} must classify via {CLASSIFIER_WORKFLOW_REF} rather than " f"its own copy of the detection logic"
    )


def test_reusable_workflow_exposes_every_area() -> None:
    """An area with no output leaves its gate reading an empty string forever."""
    workflow = yaml.safe_load(CLASSIFIER_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the `on:` key as the boolean True.
    triggers = workflow.get(True) or workflow.get("on")
    declared = set(triggers["workflow_call"]["outputs"])
    assert declared == {*AREAS, "doc-only"}, (
        f"_classify-change.yml declares outputs {sorted(declared)}, but "
        f"classify_change.py emits {sorted({*AREAS, 'doc-only'})}"
    )

    job_outputs = set(workflow["jobs"]["classify"]["outputs"])
    assert job_outputs == declared, (
        "the classify job's outputs must match the workflow_call outputs, "
        "otherwise a declared output is always empty"
    )


def test_hygiene_and_lint_jobs_stay_ungated() -> None:
    """These validate the gating itself, so they must run on every PR."""
    jobs = _load("ci.yml")["jobs"]
    for job_id in ("test", "lint-workflows"):
        assert "if" not in jobs[job_id], (
            f"ci.yml:{job_id} must stay ungated -- it is part of what verifies "
            f"that the other jobs' gating is correct"
        )


def test_required_test_job_keeps_its_context_name() -> None:
    """`test` is a required context; a `name:` here would change it.

    Branch protection matches on the check-run name, which for an Actions job
    is its `name:` or, absent that, its job id -- *not* the `Workflow / Job`
    form the UI displays. Adding a `name:` to this job renames the context, and
    the ruleset would then wait forever for a check no workflow produces --
    blocking every PR. See issue #5728.
    """
    assert "name" not in _load("ci.yml")["jobs"]["test"], (
        "ci.yml:test must not declare a `name:`; its required check context is "
        "the bare job id 'test' in .github/rulesets/default-branch-protection.json"
    )


def test_no_legacy_detection_mechanisms_remain() -> None:
    """The point of the shared classifier is that these do not come back."""
    for name in GATED_WORKFLOWS:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "dorny/paths-filter" not in text, (
            f"{name} reintroduces dorny/paths-filter; gate on the shared " f"classifier instead so all workflows agree"
        )
        assert "detect-frontend-changes" not in text
        assert "detect-iac-changes" not in text
