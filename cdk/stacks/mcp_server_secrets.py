"""Least-privilege access to the MCP server's credential parameters (#358).

The deployed MCP server needs the same credentials as a local one
(``ALLOTMINT_MCP_BRAVE_API_KEY`` for ``search_web``, ``ALLOTMINT_MCP_GITHUB_TOKEN``
for ``create_github_issue``). They live in SSM Parameter Store as SecureStrings,
created outside CloudFormation so no value is ever in a template:

    aws ssm put-parameter --type SecureString --name /allotmint/mcp/brave-api-key --value ...

The stack passes only each parameter's *name*, as ``<VARIABLE>_PARAMETER``, and
grants ``ssm:GetParameter`` on exactly those parameters.
``allotmint_pro/mcp_server/ssm_secrets.py`` resolves them into ``<VARIABLE>`` at
cold start. A parameter that was never created leaves its tool "not configured";
it does not fail the deploy or the Lambda's start.

SecureStrings encrypted with the AWS-managed ``aws/ssm`` key need no KMS grant:
that key's policy already allows decryption through SSM for principals in the
account.
"""

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

# Environment variable the MCP server reads -> SSM parameter holding its value.
MCP_SERVER_SECRET_PARAMETERS: dict[str, str] = {
    "ALLOTMINT_MCP_BRAVE_API_KEY": "/allotmint/mcp/brave-api-key",
    "ALLOTMINT_MCP_GITHUB_TOKEN": "/allotmint/mcp/github-token",
}

# Suffix of the env var that carries a parameter's name; must match
# allotmint_pro/mcp_server/ssm_secrets.py.
PARAMETER_ENV_SUFFIX = "_PARAMETER"


class McpServerSecrets(Construct):
    """Hand ``McpServerLambda`` the names of, and read access to, its credential parameters."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        self.parameter_arns = [
            stack.format_arn(
                service="ssm", resource="parameter", resource_name=name.removeprefix("/")
            )
            for name in MCP_SERVER_SECRET_PARAMETERS.values()
        ]

    def attach(self, fn: _lambda.Function) -> iam.Grant:
        """Set ``<VARIABLE>_PARAMETER`` on ``fn`` and allow it to read those parameters."""
        for variable, parameter in MCP_SERVER_SECRET_PARAMETERS.items():
            fn.add_environment(f"{variable}{PARAMETER_ENV_SUFFIX}", parameter)
        return iam.Grant.add_to_principal(
            grantee=fn,
            actions=["ssm:GetParameter"],
            resource_arns=self.parameter_arns,
        )
