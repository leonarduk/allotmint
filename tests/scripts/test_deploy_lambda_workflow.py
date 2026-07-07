"""Regression tests for the production deploy workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-lambda.yml"


def test_deploy_workflow_warms_price_snapshot() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    deploy_job = workflow["jobs"]["deploy"]
    steps = deploy_job["steps"]
    step_names = [s.get("name", "") for s in steps]

    warm_step = next(step for step in steps if step.get("name") == "Warm price snapshot")

    run_script = warm_step["run"]

    assert "aws lambda invoke" in run_script
    assert "PriceRefreshLambda" in run_script
    assert "aws s3api head-object" in run_script
    assert "prices/latest_prices.json" in run_script

    # Bucket must be resolved from CloudFormation, not from the $DATA_BUCKET secret
    # (empty/masked secrets cause exit 255 from the AWS CLI).
    assert (
        "PortfolioDataBucket" in run_script
    ), "head-object bucket must be derived from CloudFormation, not $DATA_BUCKET secret"
    assert (
        '--bucket "$DATA_BUCKET"' not in run_script
    ), "head-object must not use $DATA_BUCKET directly — secret may be masked or empty"

    # Step must run after the CDK deploy that creates the bucket.
    deploy_idx = next(i for i, name in enumerate(step_names) if "Deploy BackendLambdaStack" in name)
    warm_idx = step_names.index("Warm price snapshot")
    assert warm_idx > deploy_idx, "Warm price snapshot must run after Deploy BackendLambdaStack"


def test_deploy_workflow_verify_price_snapshot_fails_hard_on_non_404() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    deploy_job = workflow["jobs"]["deploy"]
    steps = deploy_job["steps"]

    verify_step = next(
        step for step in steps if step.get("name") == "Verify price snapshot seeded in S3"
    )

    run_script = verify_step["run"]

    # A genuine S3 error (403, 500, network failure, etc.) must hard-fail the
    # deploy rather than being swallowed as a warning.
    assert "exit 1" in run_script
    assert "::warning::Could not verify price snapshot" not in run_script

    # NoSuchKey/404 (bucket not yet seeded) must remain a soft pass.
    assert "NoSuchKey\\|Not Found\\|404" in run_script
    assert "::warning::Price snapshot" in run_script

    # head_output must capture stderr (where the AWS CLI writes error
    # details like "NoSuchKey"/"Access Denied"), otherwise the grep above
    # would never match and every error would hard-fail, including 404s.
    capture_line = next(line for line in run_script.splitlines() if "head_output=" in line)
    # The capture spans multiple continuation lines; the redirect is on the
    # final line that closes the command substitution.
    capture_block = run_script[run_script.index(capture_line) :]
    capture_end = capture_block.index(')"') + len(')"')
    assert "2>&1" in capture_block[:capture_end], (
        "head_output=$(...) must redirect stderr (2>&1) so NoSuchKey/Access "
        "Denied errors are visible to the grep below"
    )

    # The step must not swallow its own exit code via continue-on-error,
    # otherwise the hard failure above would not fail the job.
    assert "continue-on-error" not in verify_step


def test_deploy_workflow_verify_price_snapshot_retries_transient_s3_errors() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    deploy_job = workflow["jobs"]["deploy"]
    steps = deploy_job["steps"]

    verify_step = next(
        step for step in steps if step.get("name") == "Verify price snapshot seeded in S3"
    )
    run_script = verify_step["run"]

    # Transient S3 errors (throttling, 5xx, timeouts) must be retried with
    # backoff rather than failing on the first attempt.
    assert "Throttling" in run_script
    assert "sleep" in run_script
    assert "max_attempts" in run_script

    # A persistent 403/AccessDenied must still fail immediately (not match the
    # transient-error grep pattern), since retrying it would only mask a real
    # permissions problem.
    transient_grep_line = next(line for line in run_script.splitlines() if "Throttling" in line)
    assert "AccessDenied" not in transient_grep_line


def test_deploy_workflow_gh_api_with_retry_uses_single_page_sorted_lookup() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    check_ci_job = workflow["jobs"]["check-ci"]
    run_script = check_ci_job["steps"][0]["run"]

    # The ci.yml run lookup must ask the API for the latest run directly
    # instead of paging and sorting client-side (which could still miss the
    # true latest run if more runs exist than the page size).
    assert "per_page=1&sort=created&direction=desc" in run_script
    assert "sort_by(.id) | reverse" not in run_script


def test_deploy_workflow_gh_api_with_retry_includes_stderr_in_warnings() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    check_ci_job = workflow["jobs"]["check-ci"]
    run_script = check_ci_job["steps"][0]["run"]

    # Retry warnings/errors must surface the underlying `gh api` stderr so a
    # failure's actual cause (rate limit, auth, network) is visible instead of
    # a bare "gh api call failed" message.
    assert 'gh api "$@" 2>"$stderr_file"' in run_script
    assert "${err}" in run_script


def test_deploy_workflow_gh_api_with_retry_budgets_elapsed_time() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    check_ci_job = workflow["jobs"]["check-ci"]
    run_script = check_ci_job["steps"][0]["run"]

    # Retries must stop once continuing would exceed the same timeout_seconds
    # budget the outer polling loop uses, instead of retrying a fixed attempt
    # count blindly regardless of elapsed time.
    assert "start_epoch=$(date +%s)" in run_script
    assert "deadline=$((start_epoch + timeout_seconds))" in run_script
    assert 'if [ "$((now + wait_seconds))" -ge "$deadline" ]' in run_script


def test_deploy_workflow_cognito_retry_documents_why_it_remains() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    deploy_job = workflow["jobs"]["deploy"]
    steps = deploy_job["steps"]

    reconcile_step = next(
        step for step in steps if step.get("name") == "Reconcile UiAuthClient OAuth configuration"
    )
    run_script = reconcile_step["run"]

    assert "cognito_retry() {" in run_script
    # The comment must explain that the loop is still needed because the root
    # cause (IAM eventually-consistent policy propagation) is an inherent AWS
    # platform behaviour, not something a code change here can eliminate.
    assert "still needed" in run_script
    assert "eventually-consistent" in run_script or "eventually consistent" in run_script
