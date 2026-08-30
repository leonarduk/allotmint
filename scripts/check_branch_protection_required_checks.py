#!/usr/bin/env python3
"""Validate required status checks in the default branch ruleset.

This protects the documented branch protection gate from silently drifting away
from the deterministic GitHub Actions workflows that are expected to block PRs.

This script is *offline*: it only reads files in the repository, so it can run
on every PR with the default read-only `GITHUB_TOKEN`. It cannot see what
GitHub actually enforces -- that comparison lives in
`scripts/check_live_branch_protection.py`, which needs API access and runs on a
schedule. Both are needed: this one catches "a job was renamed", the live one
catches "the ruleset was never applied".

## Context naming

A required status check matches a GitHub Actions **check-run name**, which is:

* the job's `name:` if it has one, otherwise its job id -- e.g. `test`,
  `CDK infrastructure tests`; **not** the `Workflow / Job` form shown in the
  Actions UI; and
* `<caller job id> / <called job name>` for a job that delegates to a reusable
  workflow via `uses:` -- e.g. `ai-review / DeepSeek AI code review`.

Getting this wrong is not a cosmetic error: a required context that no
check-run ever produces leaves every PR pending forever. See issue #5728.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULESET_PATH = REPO_ROOT / ".github" / "rulesets" / "default-branch-protection.json"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

EXPECTED_REQUIRED_CHECKS = {
    # `test` is the ungated repo-hygiene job (branch-protection validation,
    # lockfile platform coverage, extract_verdict/review_common tests). Its
    # context string is the bare job id, so the job must never gain a `name:`
    # and must never be renamed -- see the comment on the job in ci.yml.
    "test",
    # Area-gated jobs. These skip on PRs that can't affect them, and GitHub
    # reports a skipped job as a passing required check -- which is only safe
    # because every gate is written `<area> != 'false'` with `!cancelled()`,
    # so a classifier failure runs the job rather than skipping it. See
    # scripts/classify_change.py and .github/workflows/_classify-change.yml.
    "Frontend lint, type-check and unit tests",
    # cdk/tests/ against root deps; iac-validation.yml runs the same suite
    # against cdk/requirements.txt. The backend `tests/` suite runs once,
    # under Lambda-pinned deps, in `lambda-compat` below. Keeping each suite
    # to a single dependency set avoids running `tests/` twice per PR
    # (see PR #4464).
    "CDK infrastructure tests",
    "Validate backend/requirements.txt (dry-run)",
    "Backend lint (ruff, black)",
    "Lambda-compat pytest (backend/requirements.txt)",
    "Frontend smoke tests (preview build)",
    "integration-tests",
    "require-issue-reference",
    "Check for merge conflicts with main",
    # Reusable-workflow job: the check-run name is `<caller job id> / <called
    # job name>`, which is why this one alone carries a `/`.
    "ai-review / DeepSeek AI code review",
}

# Workflows that are disabled in GitHub (`gh workflow list --all` reports
# `disabled_manually`). A disabled workflow never reports a check-run, so any
# context it would produce must stay out of the required set or every PR is
# blocked forever. Removed from the required list in #5728; re-enabling one is
# a deliberate change that must also fix why it was failing.
DISABLED_WORKFLOW_FILES = {
    "frontend-tests.yml",
    "dependency-review.yml",
    "siteplan.yml",
    "super-linter.yml",
    "claude-pr-review.yml",
    "gpt-pr-review.yml",
}


def load_ruleset_contexts() -> set[str]:
    ruleset = json.loads(RULESET_PATH.read_text(encoding="utf-8"))
    contexts: set[str] = set()

    for rule in ruleset.get("rules", []):
        if rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters", {})
        for check in parameters.get("required_status_checks", []):
            context = check.get("context")
            if isinstance(context, str):
                contexts.add(context)

    return contexts


def resolve_called_workflow_job_names(workflow_path: Path, with_inputs: dict) -> list[str]:
    """Return display names for jobs in a reusable workflow referenced via `uses:`.

    Job `name:` fields in the called workflow may reference `${{ inputs.<name> }}`
    placeholders, which are substituted using the calling job's `with:` values.
    """
    try:
        called = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        print(f"Warning: could not parse {workflow_path.name}: {exc}", file=sys.stderr)
        return []
    if not isinstance(called, dict):
        return []
    jobs = called.get("jobs")
    if not isinstance(jobs, dict):
        return []

    names: list[str] = []
    for called_job_id, called_job in jobs.items():
        job_name = called_job.get("name") if isinstance(called_job, dict) else None
        display_name = job_name if isinstance(job_name, str) else called_job_id
        for key, value in with_inputs.items():
            display_name = display_name.replace(f"${{{{ inputs.{key} }}}}", str(value))
        names.append(display_name)
    return names


def workflow_check_contexts(exclude_files: set[str] | None = None) -> set[str]:
    """Return every check-run name the repository's workflows can produce.

    `exclude_files` names workflow files to skip; it defaults to
    `DISABLED_WORKFLOW_FILES` so a required context can never resolve to a job
    that will never run. Pass an empty set to see every context, disabled
    included.
    """
    skip = DISABLED_WORKFLOW_FILES if exclude_files is None else exclude_files
    contexts: set[str] = set()

    for workflow_path in WORKFLOWS_DIR.glob("*.yml"):
        if workflow_path.name in skip:
            continue
        try:
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"Warning: could not parse {workflow_path.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(workflow, dict):
            continue
        jobs = workflow.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            uses = job.get("uses") if isinstance(job, dict) else None
            if isinstance(uses, str) and uses.startswith("./"):
                with_inputs = job.get("with", {})
                with_inputs = with_inputs if isinstance(with_inputs, dict) else {}
                called_path = REPO_ROOT / Path(uses)
                for called_name in resolve_called_workflow_job_names(called_path, with_inputs):
                    contexts.add(f"{job_id} / {called_name}")
                continue
            job_name = job.get("name") if isinstance(job, dict) else None
            display_name = job_name if isinstance(job_name, str) else job_id
            contexts.add(display_name)

    return contexts


def main() -> int:
    required_contexts = load_ruleset_contexts()
    available_contexts = workflow_check_contexts()
    errors: list[str] = []

    if required_contexts != EXPECTED_REQUIRED_CHECKS:
        missing = sorted(EXPECTED_REQUIRED_CHECKS - required_contexts)
        unexpected = sorted(required_contexts - EXPECTED_REQUIRED_CHECKS)
        if missing:
            errors.append(f"Ruleset is missing required checks: {missing}")
        if unexpected:
            errors.append(f"Ruleset has unexpected required checks: {unexpected}")

    missing_workflows = set(required_contexts) - available_contexts
    if missing_workflows:
        disabled_contexts = workflow_check_contexts(exclude_files=set()) - available_contexts
        blocked = sorted(missing_workflows & disabled_contexts)
        unknown = sorted(missing_workflows - disabled_contexts)
        if blocked:
            errors.append(
                "Required checks map to disabled workflows and can never report: " f"{blocked}"
            )
        if unknown:
            errors.append(f"Required checks do not match workflow/job names: {unknown}")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Branch protection required checks match deterministic workflow contexts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
