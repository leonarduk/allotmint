"""Least-privilege plumbing for syncing the data bucket with allotmint-data (#11037).

The Support page's "Pull from git" / "Push to git" buttons dispatch GitHub
Actions workflows in the allotmint-data repo; those workflows do the copying.
This construct provides the two AWS-side pieces they need:

* ``role``: assumable only by allotmint-data's ``main`` branch through the
  account's existing GitHub OIDC provider (the one the deploy workflow
  already uses), with read/write on the data bucket and nothing else.
* ``token_parameter_name``: the SSM SecureString holding a fine-grained
  GitHub token (Actions: write on allotmint-data only) that the backend uses
  to dispatch those workflows. SecureStrings can't be created by
  CloudFormation, so the owner creates it once (docs/DEPLOY.md).
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

DEFAULT_DATA_SYNC_REPO = "leonarduk/allotmint-data"
DATA_SYNC_TOKEN_PARAMETER = "/allotmint/data-sync/github-token"
GITHUB_OIDC_HOST = "token.actions.githubusercontent.com"


class DataSync(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, data_bucket: s3.IBucket, repo: str) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        self.repo = repo
        self.token_parameter_name = DATA_SYNC_TOKEN_PARAMETER

        provider_arn = stack.format_arn(
            service="iam", region="", resource="oidc-provider", resource_name=GITHUB_OIDC_HOST
        )
        self.role = iam.Role(
            self,
            "Role",
            description=f"Assumed by {repo} GitHub Actions on main to sync the data bucket",
            max_session_duration=Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider_arn,
                conditions={
                    "StringEquals": {
                        f"{GITHUB_OIDC_HOST}:aud": "sts.amazonaws.com",
                        # Only workflows running on main (both sync workflows
                        # are workflow_dispatch on main); no other repo, branch,
                        # tag or pull request can assume this role.
                        f"{GITHUB_OIDC_HOST}:sub": f"repo:{repo}:ref:refs/heads/main",
                    }
                },
            ),
        )
        # Pull overwrites objects and deletes the writable-accounts/ overlay
        # copies git supersedes; push reads every synced prefix.
        data_bucket.grant_read_write(self.role)

        self.token_parameter_arn = stack.format_arn(
            service="ssm", resource="parameter", resource_name=self.token_parameter_name.lstrip("/")
        )

    def grant_read_token(self, grantee: iam.IGrantable) -> iam.Grant:
        """Allow ``grantee`` to read the GitHub token used to dispatch the workflows."""

        return iam.Grant.add_to_principal(
            grantee=grantee,
            actions=["ssm:GetParameter"],
            resource_arns=[self.token_parameter_arn],
        )
