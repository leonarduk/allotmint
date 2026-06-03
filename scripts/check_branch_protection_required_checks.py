#!/usr/bin/env python3
"""Validate required status checks in the default branch ruleset.

This protects the documented branch protection gate from silently drifting away
from the deterministic GitHub Actions workflows that are expected to block PRs.
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
    "CI / test",
    "CI / Validate backend/requirements.txt (dry-run)",
    "CI / Lambda-compat pytest (backend/requirements.txt)",
    "Backend Integration Tests / integration-tests",
    "Frontend Tests / frontend-tests",
    "PR Body Issue Reference Check / require-issue-reference",
    "Dependency Review / dependency-review",
    "Claude PR Review / Claude AI code review",
    "GPT PR Review / GPT AI code review",
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


def workflow_check_contexts() -> set[str]:
    contexts: set[str] = set()

    for workflow_path in WORKFLOWS_DIR.glob("*.yml"):
        try:
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"Warning: could not parse {workflow_path.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(workflow, dict):
            continue
        workflow_name = workflow.get("name")
        jobs = workflow.get("jobs")
        if not isinstance(workflow_name, str) or not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            job_name = job.get("name") if isinstance(job, dict) else None
            display_name = job_name if isinstance(job_name, str) else job_id
            contexts.add(f"{workflow_name} / {display_name}")

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

    missing_workflows = sorted(required_contexts - available_contexts)
    if missing_workflows:
        errors.append(
            "Required checks do not match workflow/job names: "
            f"{missing_workflows}"
        )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Branch protection required checks match deterministic workflow contexts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
