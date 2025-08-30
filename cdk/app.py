#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.static_site_stack import StaticSiteStack


def _is_truthy(value) -> bool:
    """Return True for common representations of truthy values."""

    if value is None:
        return False
    return str(value).lower() in {"1", "true", "y", "yes"}


app = cdk.App()

deploy_backend_value = (
    app.node.try_get_context("deploy_backend")
    or os.getenv("DEPLOY_BACKEND")
)

if _is_truthy(deploy_backend_value):
    BackendLambdaStack(app, "BackendLambdaStack")

StaticSiteStack(app, "StaticSiteStack")
app.synth()
