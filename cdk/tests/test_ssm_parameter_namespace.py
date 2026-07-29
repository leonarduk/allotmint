import pytest
from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Match, Template
from stacks.ssm_parameter_namespace import SsmParameterNamespaceGrant


def _template(*, namespace: str = "/allotmint/moneyhub/tokens/", allow_write: bool) -> Template:
    app = App()
    stack = Stack(app, "TestStack")
    role = iam.Role(
        stack,
        "ApplicationRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    SsmParameterNamespaceGrant(
        stack,
        "NamespaceGrant",
        grantee=role,
        namespace=namespace,
        allow_write=allow_write,
    )
    return Template.from_stack(stack)


def test_grant_scopes_read_write_access_to_namespace() -> None:
    template = _template(allow_write=True)

    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        {
                            "Action": [
                                "ssm:GetParameter",
                                "ssm:GetParameters",
                                "ssm:GetParametersByPath",
                                "ssm:PutParameter",
                            ],
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


def test_grant_is_read_only_by_default() -> None:
    template = _template(namespace="reports", allow_write=False)
    policies = template.find_resources("AWS::IAM::Policy")
    statements = next(iter(policies.values()))["Properties"]["PolicyDocument"]["Statement"]
    actions = statements[0]["Action"]

    assert actions == ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    assert "ssm:PutParameter" not in actions


def test_grant_rejects_empty_namespace() -> None:
    app = App()
    stack = Stack(app, "TestStack")
    role = iam.Role(
        stack,
        "ApplicationRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    )

    with pytest.raises(
        ValueError,
        match="namespace must contain a non-empty SSM parameter path",
    ):
        SsmParameterNamespaceGrant(
            stack,
            "NamespaceGrant",
            grantee=role,
            namespace=" / ",
        )
