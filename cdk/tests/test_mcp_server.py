"""The MCP server and Bedrock wiring that chat and the agents need on AWS (#11052)."""

from __future__ import annotations

import json
import os

import pytest
from aws_cdk import App
from aws_cdk.assertions import Template
from stacks.backend_lambda_stack import (
    DEFAULT_BEDROCK_MODEL_ID,
    MCP_SERVER_HANDLER,
    BackendLambdaStack,
    _bedrock_invoke_resources,
)
from stacks.mcp_server_secrets import MCP_SERVER_SECRET_PARAMETERS


@pytest.fixture(scope="module")
def template() -> dict:
    os.environ.setdefault("JWT_SECRET", "test-secret")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    app = App(context={"data_bucket": "unit-test-data-bucket", "app_env": "aws"})
    return Template.from_stack(BackendLambdaStack(app, "McpServerTest")).to_json()


def _resources(template: dict, kind: str) -> dict:
    return {lid: r for lid, r in template["Resources"].items() if r["Type"] == kind}


def _function(template: dict, prefix: str) -> tuple[str, dict]:
    return next(
        (lid, r)
        for lid, r in _resources(template, "AWS::Lambda::Function").items()
        if lid.startswith(prefix)
    )


def _role_statements(template: dict, function_prefix: str) -> list[dict]:
    _, fn = _function(template, function_prefix)
    role_ref = fn["Properties"]["Role"]["Fn::GetAtt"][0]
    return [
        statement
        for policy in _resources(template, "AWS::IAM::Policy").values()
        if {"Ref": role_ref} in policy["Properties"]["Roles"]
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]


def _actions(statement: dict) -> list[str]:
    action = statement["Action"]
    return [action] if isinstance(action, str) else action


def test_mcp_server_runs_the_pro_handler_from_the_shared_image(template) -> None:
    _, mcp = _function(template, "McpServerLambda")
    assert mcp["Properties"]["ImageConfig"]["Command"] == [MCP_SERVER_HANDLER]
    env = mcp["Properties"]["Environment"]["Variables"]
    assert env["DISABLE_AUTH"] == "true"
    assert env["APP_ENV"] == "aws"
    for variable, parameter in MCP_SERVER_SECRET_PARAMETERS.items():
        assert env[f"{variable}_PARAMETER"] == parameter


def test_mcp_function_url_requires_iam_signing(template) -> None:
    (url,) = _resources(template, "AWS::Lambda::Url").values()
    assert url["Properties"]["AuthType"] == "AWS_IAM"
    mcp_id, _ = _function(template, "McpServerLambda")
    assert url["Properties"]["TargetFunctionArn"] == {"Fn::GetAtt": [mcp_id, "Arn"]}
    assert "McpServerFunctionUrl" in template["Outputs"]


@pytest.mark.parametrize("caller", ["BackendLambda", "DataStewardLambda"])
def test_callers_get_the_mcp_url_and_may_invoke_it(template, caller) -> None:
    _, fn = _function(template, caller)
    url = fn["Properties"]["Environment"]["Variables"]["MCP_SERVER_URL"]
    assert "/mcp" in json.dumps(url)
    mcp_id, _ = _function(template, "McpServerLambda")
    invoke = {
        action
        for statement in _role_statements(template, caller)
        if mcp_id in json.dumps(statement["Resource"])
        for action in _actions(statement)
    }
    assert {"lambda:InvokeFunctionUrl", "lambda:InvokeFunction"} <= invoke


def test_only_the_backend_and_steward_may_invoke_the_mcp_server(template) -> None:
    mcp_id, _ = _function(template, "McpServerLambda")
    granted = set()
    for lid, fn in _resources(template, "AWS::Lambda::Function").items():
        role_ref = fn["Properties"]["Role"]["Fn::GetAtt"][0]
        for policy in _resources(template, "AWS::IAM::Policy").values():
            if {"Ref": role_ref} not in policy["Properties"]["Roles"]:
                continue
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
                if mcp_id in json.dumps(statement["Resource"]) and any(
                    a.startswith("lambda:Invoke") for a in _actions(statement)
                ):
                    granted.add(lid)
    assert len(granted) == 2
    assert {
        next(p for p in ("BackendLambda", "DataStewardLambda") if lid.startswith(p))
        for lid in granted
    } == {
        "BackendLambda",
        "DataStewardLambda",
    }


def test_mcp_server_cannot_write_or_delete_in_the_bucket(template) -> None:
    for statement in _role_statements(template, "McpServerLambda"):
        for action in _actions(statement):
            assert not action.startswith(("s3:Put", "s3:Delete")), action


def test_bedrock_grant_is_scoped_to_the_configured_profile(template) -> None:
    _, backend = _function(template, "BackendLambda")
    assert (
        backend["Properties"]["Environment"]["Variables"]["BEDROCK_MODEL_ID"]
        == DEFAULT_BEDROCK_MODEL_ID
    )
    bedrock = [
        s
        for s in _role_statements(template, "BackendLambda")
        if "bedrock:InvokeModel" in _actions(s)
    ]
    assert bedrock, "BackendLambda needs Bedrock for chat"
    for statement in bedrock:
        assert "foundation-model/*" not in json.dumps(statement["Resource"])
    (model_statement,) = [s for s in bedrock if "foundation-model/" in json.dumps(s["Resource"])]
    assert "bedrock:InferenceProfileArn" in json.dumps(model_statement["Condition"])


def test_bedrock_resources_for_a_profile_and_a_bare_model() -> None:
    profiles, models = _bedrock_invoke_resources(
        region="eu-west-1", account="1", model_id="eu.amazon.nova-lite-v1:0"
    )
    assert profiles == ["arn:aws:bedrock:eu-west-1:1:inference-profile/eu.amazon.nova-lite-v1:0"]
    assert "arn:aws:bedrock:eu-central-1::foundation-model/amazon.nova-lite-v1:0" in models
    assert _bedrock_invoke_resources(
        region="eu-west-1", account="1", model_id="amazon.nova-lite-v1:0"
    ) == (
        [],
        ["arn:aws:bedrock:eu-west-1::foundation-model/amazon.nova-lite-v1:0"],
    )
