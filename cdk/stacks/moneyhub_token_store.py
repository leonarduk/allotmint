"""Infrastructure contract for per-owner Moneyhub OAuth token storage."""

from aws_cdk import ArnFormat, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class MoneyhubTokenStore(Construct):
    """Grant access to the SecureString parameters in the Moneyhub namespace.

    Token parameters are created lazily by the application because there is one
    JSON document per owner. CloudFormation cannot provision an open-ended set
    of owners and ``AWS::SSM::Parameter`` does not support ``SecureString``, so
    this construct deliberately owns the namespace IAM contract rather than a
    placeholder plaintext parameter.
    """

    PARAMETER_PATH = "/allotmint/moneyhub/tokens"

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        self.parameter_path = self.PARAMETER_PATH
        self.storage_uri = f"ssm://{self.parameter_path}"
        self.parameter_arn = Stack.of(self).format_arn(
            service="ssm",
            resource="parameter",
            resource_name=f"{self.parameter_path.lstrip('/')}/*",
            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
        )

    def grant_read_write(self, grantee: iam.IGrantable) -> iam.Grant:
        """Allow ``grantee`` to decrypt, read, and update owner token sets."""

        return iam.Grant.add_to_principal(
            grantee=grantee,
            actions=["ssm:GetParameter", "ssm:PutParameter"],
            resource_arns=[self.parameter_arn],
        )
