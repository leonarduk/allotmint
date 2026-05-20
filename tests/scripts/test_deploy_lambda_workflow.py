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
