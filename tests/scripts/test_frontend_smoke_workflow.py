"""Regression tests guarding the frontend-smoke CI job and its build output."""

from __future__ import annotations

from pathlib import Path

import yaml

CI_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-lambda.yml"


def _step_name(step: dict) -> str:
    return step.get("name", "") or ""


def _step_run(step: dict) -> str:
    return step.get("run", "") or ""


def _first_step_index(steps: list[dict], matcher) -> int | None:
    """Return the index of the first step in ``steps`` for which ``matcher(step)`` is truthy.

    Shared by the step-ordering tests below (frontend-smoke build-before-playwright,
    deploy-lambda build-before-deploy), which all scan a workflow job's steps for
    the first one matching some name/run substring (#5324 follow-up).
    """
    for i, step in enumerate(steps):
        if matcher(step):
            return i
    return None


def test_frontend_smoke_build_preview_before_playwright() -> None:
    """The frontend-smoke job must build before running Playwright tests.

    If build:preview is reordered to run after the Playwright step, the smoke
    tests would run against stale or non-existent build output.  This test
    checks semantic content (step name or run text) rather than hardcoded step
    indices, so unrelated prepended or inserted steps don't break it.
    """
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["frontend-smoke"]["steps"]

    build_idx = _first_step_index(
        steps, lambda step: "Build preview" in _step_name(step) or "build:preview" in _step_run(step)
    )
    playwright_idx = _first_step_index(
        steps,
        lambda step: "Run frontend smoke tests" in _step_name(step) or "playwright test" in _step_run(step),
    )

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

    assert needed is not None, "verify-smoke-tests job must declare a needs: dependency on smoke-test"

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
    assert "smoke-test" in needed_jobs, f"verify-smoke-tests must need smoke-test, but needs: is {needed_jobs}"


def test_frontend_smoke_builds_preview_before_running_playwright() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))

    smoke_job = workflow["jobs"]["frontend-smoke"]
    steps = smoke_job["steps"]

    build_idx = _first_step_index(steps, lambda step: "build:preview" in _step_run(step))
    playwright_idx = _first_step_index(steps, lambda step: "playwright test" in _step_run(step))

    assert build_idx is not None, "frontend-smoke job has no step running 'npm run build:preview'"
    assert playwright_idx is not None, "frontend-smoke job has no step running a Playwright test command"
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


def test_deploy_lambda_step_order() -> None:
    """The deploy job in deploy-lambda.yml must build before it deploys.

    If "Build frontend" is reordered to run after the first "cdk deploy"
    step, the deploy would ship stale frontend assets. This checks semantic
    content (step name/run text) rather than hardcoded indices, so unrelated
    inserted/reordered steps elsewhere in the job don't break it.
    """
    workflow = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]

    build_idx = _first_step_index(
        steps, lambda step: "Build frontend" in _step_name(step) or "npm run build" in _step_run(step)
    )
    deploy_idx = _first_step_index(
        steps, lambda step: "cdk deploy" in _step_run(step) or _step_name(step).startswith("Deploy ")
    )

    assert build_idx is not None, (
        "deploy job has no step that builds the frontend "
        "(expected a step with 'Build frontend' in its name or 'npm run build' in its run)"
    )
    assert deploy_idx is not None, (
        "deploy job has no step that deploys infrastructure "
        "(expected a step with 'cdk deploy' in its run or a name starting with 'Deploy ')"
    )
    assert build_idx < deploy_idx, (
        "Build step must run before the first deploy step in the deploy job. "
        f"Found build at index {build_idx}, deploy at index {deploy_idx}."
    )


def test_verify_smoke_tests_job_declared_after_its_dependency_chain() -> None:
    """verify-smoke-tests must be declared after check-ci, deploy, and smoke-test.

    PyYAML's safe_load preserves mapping key order for Python 3.7+, so the
    `jobs` dict's iteration order mirrors the job declaration order in the
    YAML file itself. This guards the human-readable top-to-bottom flow of
    deploy-lambda.yml (check-ci -> deploy -> smoke-test -> verify-smoke-tests):
    if verify-smoke-tests were accidentally moved above one of its
    dependencies in the file, the `needs:` wiring would still be functionally
    correct (GitHub Actions doesn't care about declaration order), but the
    file would become confusing to read top-to-bottom and easy to
    misunderstand during review. This is a structural/readability check
    distinct from test_deploy_workflow_verify_smoke_tests_references_existing_job
    above, which only checks the needs: reference is valid, not the file
    ordering.
    """
    workflow = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job_order = list(workflow["jobs"].keys())

    expected_chain = ["check-ci", "deploy", "smoke-test", "verify-smoke-tests"]
    for job_id in expected_chain:
        assert job_id in job_order, f"Expected job {job_id!r} not found in deploy-lambda.yml"

    actual_indices = [job_order.index(job_id) for job_id in expected_chain]
    assert actual_indices == sorted(actual_indices), (
        "Jobs in deploy-lambda.yml must be declared in dependency order "
        f"(check-ci, deploy, smoke-test, verify-smoke-tests) for readability, "
        f"but found declaration order {job_order}"
    )


def test_verify_smoke_tests_transitively_depends_on_deploy_and_check_ci() -> None:
    """verify-smoke-tests's needs: chain must resolve all the way back to check-ci.

    verify-smoke-tests directly needs only smoke-test (see
    test_deploy_workflow_verify_smoke_tests_references_existing_job above),
    but the gate is only meaningful if that chain is unbroken back to the
    first job. If smoke-test's own needs: were ever changed to drop deploy
    (or deploy's needs: dropped check-ci), verify-smoke-tests could pass
    without the CI-gate or the actual deploy ever having run.
    """
    workflow = yaml.safe_load(DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    def needs_of(job_id: str) -> list[str]:
        needs = jobs[job_id].get("needs")
        if needs is None:
            return []
        return [needs] if isinstance(needs, str) else list(needs)

    assert "smoke-test" in needs_of("verify-smoke-tests")
    assert "deploy" in needs_of("smoke-test")
    assert "check-ci" in needs_of("deploy")
