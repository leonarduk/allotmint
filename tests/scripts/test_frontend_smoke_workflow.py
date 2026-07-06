"""Regression tests guarding the frontend-smoke CI job and its build output."""

from __future__ import annotations

from pathlib import Path

import yaml

CI_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-lambda.yml"
)


def _step_run(step: dict) -> str:
    return step.get("run", "") or ""


def test_frontend_smoke_builds_preview_before_running_playwright() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))

    smoke_job = workflow["jobs"]["frontend-smoke"]
    steps = smoke_job["steps"]

    build_idx = next(
        i for i, step in enumerate(steps) if "build:preview" in _step_run(step)
    )
    playwright_idx = next(
        i for i, step in enumerate(steps) if "playwright test" in _step_run(step)
    )

    assert build_idx < playwright_idx, (
        "frontend-smoke must run 'npm run build:preview' before the Playwright "
        "test step, otherwise smoke tests would run against a stale/missing build"
    )


def test_deploy_workflow_verify_smoke_tests_references_existing_job() -> None:
    workflow = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))

    jobs = workflow["jobs"]
    verify_job = jobs["verify-smoke-tests"]

    needs = verify_job["needs"]
    needed_jobs = [needs] if isinstance(needs, str) else list(needs)

    for job_name in needed_jobs:
        assert job_name in jobs, (
            f"verify-smoke-tests needs '{job_name}', but no such job exists in "
            "deploy-lambda.yml — the referenced job may have been renamed"
        )
