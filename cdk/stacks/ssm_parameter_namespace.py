"""Least-privilege IAM grants for an SSM Parameter Store path."""

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class SsmParameterNamespaceGrant(Construct):
    """Grant a principal access to parameters below one namespace."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        grantee: iam.IGrantable,
        namespace: str,
        allow_write: bool = False,
    ) -> None:
        super().__init__(scope, construct_id)

        normalized_namespace = namespace.strip().strip("/")
        if not normalized_namespace:
            raise ValueError("namespace must contain a non-empty SSM parameter path")

        actions = [
            "ssm:GetParameter",
            "ssm:GetParameters",
            "ssm:GetParametersByPath",
        ]
        if allow_write:
            actions.append("ssm:PutParameter")

        parameter_arn = Stack.of(self).format_arn(
            service="ssm",
            resource="parameter",
            resource_name=f"{normalized_namespace}/*",
        )
        self.grant = iam.Grant.add_to_principal(
            grantee=grantee,
            actions=actions,
            resource_arns=[parameter_arn],
        )
