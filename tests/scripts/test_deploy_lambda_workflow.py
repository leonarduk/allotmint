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

    warm_step = next(
        step for step in steps if step.get("name") == "Warm price snapshot"
    )

    run_script = warm_step["run"]

    assert "aws lambda invoke" in run_script
    assert "PriceRefreshLambda" in run_script
    assert "aws s3api head-object" in run_script
    assert "prices/latest_prices.json" in run_script

    # Bucket must be resolved from CloudFormation, not from the $DATA_BUCKET secret
    # (empty/masked secrets cause exit 255 from the AWS CLI).
    assert "PortfolioDataBucket" in run_script, (
        "head-object bucket must be derived from CloudFormation, not $DATA_BUCKET secret"
    )
    assert '--bucket "$DATA_BUCKET"' not in run_script, (
        "head-object must not use $DATA_BUCKET directly — secret may be masked or empty"
    )

    # Step must run after the CDK deploy that creates the bucket.
    deploy_idx = next(
        i for i, name in enumerate(step_names) if "Deploy BackendLambdaStack" in name
    )
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
    capture_line = next(
        line for line in run_script.splitlines() if "head_output=" in line
    )
    # The capture spans multiple continuation lines; the redirect is on the
    # final line that closes the command substitution.
    capture_block = run_script[run_script.index(capture_line):]
    capture_end = capture_block.index(")\"") + len(")\"")
    assert "2>&1" in capture_block[:capture_end], (
        "head_output=$(...) must redirect stderr (2>&1) so NoSuchKey/Access "
        "Denied errors are visible to the grep below"
    )

    # The step must not swallow its own exit code via continue-on-error,
    # otherwise the hard failure above would not fail the job.
    assert "continue-on-error" not in verify_step

    # head_exit must be captured immediately after the head_output subshell
    # runs — on the same logical statement, via the
    # `&& head_exit=0 || head_exit=$?` idiom — not by a later, separate
    # `head_exit=$?` statement. Any intervening command (e.g. the `grep`
    # below) would overwrite `$?` before it is captured, leaving head_exit
    # stale. The statement spans several continuation lines, so find the
    # first line after the capture_block's closing `)"` and confirm
    # head_exit is assigned there, before any other statement runs.
    statement_end = capture_block.index("\n", capture_end)
    head_exit_statement = capture_block[capture_end:statement_end]
    assert "head_exit=" in head_exit_statement, (
        "head_exit must be captured in the same statement as the "
        "head_output subshell (e.g. `&& head_exit=0 || head_exit=$?` "
        "immediately after the closing `)\"`), not via a later, separate "
        "statement that could capture a different command's exit code"
    )
    # Explicitly verify the ordering, not just co-occurrence: head_output's
    # assignment (start of capture_block, by construction) must precede
    # head_exit's capture — i.e. head_exit= must not appear before the
    # closing `)"` of the head_output subshell — so head_output is fully
    # populated by the time head_exit is captured.
    head_output_pos = capture_block.index("head_output=")
    head_exit_pos = capture_block.index("head_exit=")
    assert head_output_pos < capture_end <= head_exit_pos, (
        "head_output must be fully assigned (subshell closed) before "
        "head_exit is captured"
    )
