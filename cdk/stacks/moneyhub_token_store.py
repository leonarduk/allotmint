"""Least-privilege access to Moneyhub OAuth token parameters."""

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

MONEYHUB_TOKEN_PARAMETER_PREFIX = "/allotmint/moneyhub/tokens"


class MoneyhubTokenStore(Construct):
    """Represent the per-owner SecureString namespace used by Moneyhub.

    Parameters are created lazily by the application because an owner is not
    known when the stack is deployed. This construct deliberately grants only
    the two SSM operations used by ``ParameterStoreJSONStorage`` and scopes
    them to descendants of the token prefix.
    """

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        self.parameter_prefix = MONEYHUB_TOKEN_PARAMETER_PREFIX
        self.parameter_arn = Stack.of(self).format_arn(
            service="ssm",
            resource="parameter",
            resource_name=f"{self.parameter_prefix.lstrip('/')}/*",
        )

    def grant_read_write(self, grantee: iam.IGrantable) -> iam.Grant:
        """Allow ``grantee`` to load and persist per-owner token blobs."""

        return iam.Grant.add_to_principal(
            grantee=grantee,
            actions=["ssm:GetParameter", "ssm:PutParameter"],
            resource_arns=[self.parameter_arn],
        )
