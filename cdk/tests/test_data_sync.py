"""The data-sync role and token grant stay least-privilege (#11037)."""

from __future__ import annotations

import json
import os

from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.assertions import Template
from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.data_sync import DATA_SYNC_TOKEN_PARAMETER, DataSync


def _construct_template(repo: str = "leonarduk/allotmint-data") -> dict:
    app = App()
    stack = Stack(app, "TestStack")
    bucket = s3.Bucket(stack, "Bucket")
    grantee = iam.Role(stack, "Grantee", assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))
    data_sync = DataSync(stack, "DataSync", data_bucket=bucket, repo=repo)
    data_sync.grant_read_token(grantee)
    return Template.from_stack(stack).to_json()


def _sync_role(template: dict) -> dict:
    return next(
        resource
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == "AWS::IAM::Role" and logical_id.startswith("DataSyncRole")
    )


def test_role_is_assumable_only_from_the_data_repo_main_branch() -> None:
    statement = _sync_role(_construct_template())["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(statement) == 1
    (trust,) = statement
    assert trust["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert "oidc-provider/token.actions.githubusercontent.com" in json.dumps(trust["Principal"])
    assert trust["Condition"] == {
        "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": "repo:leonarduk/allotmint-data:ref:refs/heads/main",
        }
    }


def _role_statements(template: dict) -> list[dict]:
    return [
        statement
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == "AWS::IAM::Policy" and logical_id.startswith("DataSyncRole")
        for statement in resource["Properties"]["PolicyDocument"]["Statement"]
    ]


def _actions(statement: dict) -> list[str]:
    action = statement["Action"]
    return [action] if isinstance(action, str) else action


def test_role_permissions_are_limited_to_the_data_bucket() -> None:
    statements = _role_statements(_construct_template())
    assert statements, "sync role should have an inline bucket policy"
    for statement in statements:
        assert all(action.startswith("s3:") for action in _actions(statement))
        assert "Bucket" in json.dumps(statement["Resource"])
        assert "s3:DeleteBucket" not in _actions(statement)


def test_role_can_delete_only_the_writable_accounts_overlay() -> None:
    deletes = [
        statement
        for statement in _role_statements(_construct_template())
        if any(action.startswith("s3:DeleteObject") for action in _actions(statement))
    ]
    assert len(deletes) == 1
    resource = json.dumps(deletes[0]["Resource"])
    assert "/writable-accounts/*" in resource
    assert '"/*"' not in resource


def test_token_grant_reads_only_the_one_parameter() -> None:
    template = _construct_template()
    grantee_policy = next(
        resource
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == "AWS::IAM::Policy" and logical_id.startswith("Grantee")
    )
    (statement,) = grantee_policy["Properties"]["PolicyDocument"]["Statement"]
    assert statement["Action"] == "ssm:GetParameter"
    assert f"parameter{DATA_SYNC_TOKEN_PARAMETER}" in json.dumps(statement["Resource"])


def test_backend_lambda_is_wired_to_the_data_sync() -> None:
    os.environ.setdefault("JWT_SECRET", "test-secret")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    app = App(context={"data_bucket": "unit-test-data-bucket", "app_env": "aws"})
    template = Template.from_stack(BackendLambdaStack(app, "BackendLambdaStackTest")).to_json()

    backend_fn = next(
        resource
        for logical_id, resource in template["Resources"].items()
        if resource["Type"] == "AWS::Lambda::Function" and logical_id.startswith("BackendLambda")
    )
    env = backend_fn["Properties"]["Environment"]["Variables"]
    assert env["DATA_SYNC_REPO"] == "leonarduk/allotmint-data"
    assert env["DATA_SYNC_TOKEN_PARAMETER"] == DATA_SYNC_TOKEN_PARAMETER
    assert "DataSyncRoleArn" in template["Outputs"]

    ssm_statements = [
        statement
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
        for statement in resource["Properties"]["PolicyDocument"]["Statement"]
        if "ssm:GetParameter" in json.dumps(statement["Action"]) and DATA_SYNC_TOKEN_PARAMETER in json.dumps(statement)
    ]
    assert len(ssm_statements) == 1
    (statement,) = ssm_statements
    assert statement["Action"] == "ssm:GetParameter"
