"""Regression tests for the frontend-smoke workflow and related CI structure."""

from __future__ import annotations

from pathlib import Path

import yaml


CI_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-lambda.yml"
)


def test_frontend_smoke_build_preview_before_playwright() -> None:
    """The frontend-smoke job must build before running Playwright tests.

    If build:preview is reordered to run after the Playwright step, the smoke
    tests would run against stale or non-existent build output.  This test
    checks semantic content (step name or run text) rather than hardcoded step
    indices, so unrelated prepended or inserted steps don't break it.
    """
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["frontend-smoke"]
    steps = job["steps"]

    build_idx: int | None = None
    playwright_idx: int | None = None

    for i, step in enumerate(steps):
        name = step.get("name", "")
        run = step.get("run", "")
        if "Build preview" in name or "build:preview" in run:
            build_idx = i
        if "Run frontend smoke tests" in name or "playwright test" in run:
            playwright_idx = i

    assert build_idx is not None, (
        "frontend-smoke job has no step that builds the frontend "
        "(expected a step with 'Build preview' in its name or 'build:preview' in its run)"
    )
    assert playwright_idx is not None, (
        "frontend-smoke job has no Playwright test step "
        "(expected a step with 'Run frontend smoke tests' in its name "
        "or 'playwright test' in its run)"
    )
    assert build_idx < playwright_idx, (
        "Build step must run before Playwright test step in frontend-smoke job. "
        f"Found build at index {build_idx}, Playwright at index {playwright_idx}."
    )


def test_verify_smoke_tests_needs_existing_job() -> None:
    """verify-smoke-tests needs: must reference a job that exists in deploy-lambda.yml.

    If the smoke-test job is renamed without updating verify-smoke-tests's needs:
    list, the deploy workflow's post-deploy validation would silently break
    (the needs: dependency would resolve to a non-existent job, which GitHub
    Actions would treat as an error during workflow dispatch).
    """
    workflow = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))

    # To keep the test readable, look specifically for verify-smoke-tests.
    # If the job id ever changes, this test will need an update — but that is
    # an explicit, rare change that justifies a deliberate update to the test.
    verify_job = workflow["jobs"]["verify-smoke-tests"]
    needed = verify_job.get("needs")

    assert needed is not None, (
        "verify-smoke-tests job must declare a needs: dependency on smoke-test"
    )

    # needs: can be a string or a list — normalise to a list for comparison.
    needed_jobs = [needed] if isinstance(needed, str) else list(needed)

    existing_jobs = set(workflow["jobs"].keys())
    for needed_id in needed_jobs:
        assert needed_id in existing_jobs, (
            f"verify-smoke-tests references job {needed_id!r} in its needs: "
            f"but no job with that id exists in deploy-lambda.yml. "
            f"Existing job ids: {sorted(existing_jobs)}"
        )

    # Explicitly verify that smoke-test (the job that runs the actual smoke
    # checks) is among the needed jobs — this is the critical dependency
    # that validates pass/fail propagation.
    assert "smoke-test" in needed_jobs, (
        f"verify-smoke-tests must need smoke-test, but needs: is {needed_jobs}"
    )
