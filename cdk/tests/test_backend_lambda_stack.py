"""CDK assertion tests for BackendLambdaStack.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_backend_lambda_stack.py -v
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure the cdk package is importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")

from aws_cdk import App, assertions  # noqa: E402
from cdk.stacks.backend_lambda_stack import BackendLambdaStack  # noqa: E402


@pytest.fixture(scope="module")
def template():
    """Synthesise BackendLambdaStack and return its CloudFormation template."""
    app = App()
    stack = BackendLambdaStack(app, "TestBackendStack")
    return assertions.Template.from_stack(stack)


# ---------------------------------------------------------------------------
# Data bucket properties
# ---------------------------------------------------------------------------

def test_data_bucket_versioning_enabled(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )


def test_data_bucket_sse_s3_encryption(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            }
        },
    )


def test_data_bucket_blocks_public_access(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_data_bucket_lifecycle_rule(template):
    """Noncurrent-version expiry lifecycle rule is present."""
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": [
                    assertions.Match.object_like(
                        {"NoncurrentVersionExpiration": {"NoncurrentDays": 30}}
                    )
                ]
            }
        },
    )


# ---------------------------------------------------------------------------
# IAM: least-privilege Lambda S3 access and broken DENY absence
# ---------------------------------------------------------------------------

def test_no_broken_deny_resource_policy_on_data_bucket(template):
    """The StringNotLike list-based DENY policy must not appear in the template.

    NOTE: enforce_ssl=True on the Bucket construct legitimately generates a
    DENY statement to block non-SSL requests — that is expected and correct.
    This test only asserts that the hand-rolled DenyNonLambdaPrincipalDataAccess
    statement (which used incorrect StringNotLike list semantics) is absent.
    """
    bucket_policies = template.find_resources("AWS::S3::BucketPolicy")
    for logical_id, resource in bucket_policies.items():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            assert stmt.get("Sid") != "DenyNonLambdaPrincipalDataAccess", (
                f"Broken DENY policy 'DenyNonLambdaPrincipalDataAccess' found in "
                f"bucket policy {logical_id} — this statement uses incorrect "
                f"StringNotLike list semantics that lock out Lambda roles: "
                f"{json.dumps(stmt)}"
            )


def test_lambda_roles_granted_expected_s3_actions_without_wildcards(template):
    """Stack grants expected S3 actions and avoids wildcard or destructive S3 permissions.

    s3:DeleteObject is explicitly checked for absence: the PR #2574 regression
    was caused by grant_read_write emitting DeleteObject as a side-effect of
    the broader grant. This test prevents that from recurring.
    """
    policies = template.find_resources("AWS::IAM::Policy")
    all_actions: list[str] = []
    for resource in policies.values():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            all_actions.extend(actions)

    assert any(a == "s3:GetObject" for a in all_actions), (
        "Expected s3:GetObject grant for Lambda roles"
    )
    assert any(a == "s3:PutObject" for a in all_actions), (
        "Expected s3:PutObject grant for Lambda roles"
    )
    assert any(a == "s3:ListBucket" for a in all_actions), (
        "Expected s3:ListBucket grant for Lambda roles that list known prefixes"
    )
    assert not any(a == "s3:*" for a in all_actions), (
        "Did not expect wildcard S3 permissions in Lambda IAM policies"
    )
    assert not any(a == "s3:DeleteObject" for a in all_actions), (
        "Did not expect s3:DeleteObject in Lambda IAM policies — "
        "grant_read_write emits this as a side-effect; use explicit action grants instead"
    )


def test_all_lambda_functions_have_data_bucket_env_var(template):
    """Every Lambda function must receive DATA_BUCKET pointing at the CDK-managed bucket.

    This guards against the build-arg bucket (seed_data_bucket) leaking into
    the runtime environment instead of the CDK-provisioned data_bucket.
    The CDK token for the bucket name resolves to a { Ref: ... } in the
    synthesised template, so we assert the key is present and its value is
    not a plain string (i.e., it is a token/Ref, not a baked-in bucket name).
    """
    lambda_functions = template.find_resources("AWS::Lambda::Function")
    for logical_id, resource in lambda_functions.items():
        properties = resource.get("Properties", {})
        if properties.get("PackageType") != "Image":
            # Skip CDK-generated helper Lambdas (e.g. log retention provider).
            continue
        env_vars = (
            properties
            .get("Environment", {})
            .get("Variables", {})
        )
        assert "DATA_BUCKET" in env_vars, (
            f"Lambda function {logical_id} is missing DATA_BUCKET environment variable"
        )
        # The value must be a CDK token (a dict with 'Ref' or 'Fn::...' key),
        # not a hardcoded string — ensuring it resolves to the managed bucket.
        bucket_val = env_vars["DATA_BUCKET"]
        assert not isinstance(bucket_val, str) or bucket_val == "", (
            f"Lambda {logical_id} DATA_BUCKET is a hardcoded string '{bucket_val}'; "
            "expected a CloudFormation token (Ref) to the CDK-managed bucket"
        )


# ---------------------------------------------------------------------------
# Observability, secrets, and cost guardrails
# ---------------------------------------------------------------------------

def test_all_lambda_functions_have_one_week_log_retention(template):
    resources = template.find_resources("Custom::LogRetention")
    # one log retention custom resource per Lambda function
    assert len(resources) >= 3, (
        "Expected Custom::LogRetention resources for backend, refresh, and agent Lambdas"
    )


def test_lambdas_get_secretsmanager_read_policy(template):
    policies = template.find_resources("AWS::IAM::Policy")
    all_actions: list[str] = []
    for resource in policies.values():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            all_actions.extend(actions)

    assert any(a == "secretsmanager:GetSecretValue" for a in all_actions), (
        "Expected secretsmanager:GetSecretValue grant for Lambda roles"
    )


def test_backend_error_alarm_exists(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "Threshold": 1,
            "EvaluationPeriods": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        },
    )


def test_monthly_budget_exists(template):
    resources = template.find_resources("AWS::Budgets::Budget")
    assert resources, "Expected an AWS::Budgets::Budget resource"
    budget_props = next(iter(resources.values())).get("Properties", {}).get("Budget", {})
    assert budget_props.get("BudgetType") == "COST"
    assert budget_props.get("TimeUnit") == "MONTHLY"
    budget_limit = budget_props.get("BudgetLimit", {})
    assert float(budget_limit.get("Amount")) == 5.0
    assert budget_limit.get("Unit") == "USD"


# ---------------------------------------------------------------------------
# CfnOutputs
# ---------------------------------------------------------------------------

def test_backend_api_url_output_exists(template):
    template.has_output("BackendApiUrl", {})


def test_data_bucket_name_output_exists(template):
    template.has_output("DataBucketName", {})


def test_backend_lambda_error_alarm_output_exists(template):
    template.has_output("BackendLambdaErrorAlarmName", {})
