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
# IAM: Lambda roles get read/write on the data bucket; no DENY policy present
# ---------------------------------------------------------------------------

def test_no_deny_resource_policy_on_data_bucket(template):
    """The broken StringNotLike DENY policy must not appear in the template."""
    bucket_policies = template.find_resources("AWS::S3::BucketPolicy")
    for logical_id, resource in bucket_policies.items():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            assert stmt.get("Effect") != "Deny", (
                f"Unexpected DENY statement in bucket policy {logical_id}: {json.dumps(stmt)}"
            )


def test_lambda_roles_granted_read_write(template):
    """At least one IAM policy grants S3 read/write actions to a Lambda role."""
    # grant_read_write generates managed/inline policies; we check that
    # s3:GetObject and s3:PutObject appear somewhere in the IAM policies.
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

    assert any("s3:GetObject" in a or a == "s3:*" for a in all_actions), (
        "Expected s3:GetObject grant for Lambda roles"
    )
    assert any("s3:PutObject" in a or a == "s3:*" for a in all_actions), (
        "Expected s3:PutObject grant for Lambda roles"
    )


# ---------------------------------------------------------------------------
# CfnOutputs
# ---------------------------------------------------------------------------

def test_backend_api_url_output_exists(template):
    template.has_output("BackendApiUrl", {})


def test_data_bucket_name_output_exists(template):
    template.has_output("DataBucketName", {})
