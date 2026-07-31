from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Match, Template
from stacks.moneyhub_token_store import (
    MONEYHUB_TOKEN_PARAMETER_PREFIX,
    MoneyhubTokenStore,
)


def test_grant_is_scoped_to_moneyhub_token_descendants() -> None:
    app = App()
    stack = Stack(app, "TestStack")
    role = iam.Role(
        stack,
        "Role",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    token_store = MoneyhubTokenStore(stack, "TokenStore")

    token_store.grant_read_write(role)

    Template.from_stack(stack).has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        {
                            "Action": ["ssm:GetParameter", "ssm:PutParameter"],
                            "Effect": "Allow",
                            "Resource": {
                                "Fn::Join": [
                                    "",
                                    [
                                        "arn:",
                                        {"Ref": "AWS::Partition"},
                                        ":ssm:",
                                        {"Ref": "AWS::Region"},
                                        ":",
                                        {"Ref": "AWS::AccountId"},
                                        ":parameter/allotmint/moneyhub/tokens/*",
                                    ],
                                ]
                            },
                        }
                    ]
                )
            }
        },
    )


def test_token_prefix_is_stable() -> None:
    assert MONEYHUB_TOKEN_PARAMETER_PREFIX == "/allotmint/moneyhub/tokens"
