"""Tests for the Moneyhub token-storage infrastructure contract."""

import os

from aws_cdk import App
from aws_cdk.assertions import Match, Template
from stacks.backend_lambda_stack import BackendLambdaStack


def _template() -> Template:
    os.environ.setdefault("JWT_SECRET", "test-secret")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    app = App(context={"data_bucket": "unit-test-data-bucket", "app_env": "aws"})
    return Template.from_stack(BackendLambdaStack(app, "MoneyhubTokenStoreTest"))


def test_backend_lambda_receives_moneyhub_token_namespace() -> None:
    _template().has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": Match.object_like({"MONEYHUB_TOKEN_STORAGE_BASE": ("ssm:///allotmint/moneyhub/tokens")})
            }
        },
    )


def test_backend_lambda_can_only_read_and_write_moneyhub_token_parameters() -> None:
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": ["ssm:GetParameter", "ssm:PutParameter"],
                                "Effect": "Allow",
                                "Resource": {
                                    "Fn::Join": Match.array_with(
                                        [
                                            Match.array_with(
                                                [Match.string_like_regexp("parameter/allotmint/moneyhub/tokens/\\\\*")]
                                            )
                                        ]
                                    )
                                },
                            }
                        )
                    ]
                )
            }
        },
    )
    assert template.find_resources("AWS::SSM::Parameter") == {}
