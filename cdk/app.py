#!/usr/bin/env python3

import aws_cdk as cdk
from aws_cdk import Fn

from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.static_site_stack import StaticSiteStack

app = cdk.App()

# Always include the backend stack so it can be deployed without
# providing a context flag or environment variable.
backend_stack = BackendLambdaStack(app, "BackendLambdaStack")

# Use Fn.import_value to resolve the API URL from BackendLambdaStack's explicit
# CfnOutput export.  Passing backend_stack.backend_api_url (a Fn::GetAtt token)
# directly to Source.json_data() caused CDK to embed the raw Fn::GetAtt in
# StaticSiteStack's template, referencing a resource that doesn't exist there.
static_stack = StaticSiteStack(
    app,
    "StaticSiteStack",
    api_base_url=Fn.import_value("BackendLambdaStack-BackendApiUrl"),
)
# Ensure BackendLambdaStack is fully deployed (and its export published) before
# StaticSiteStack attempts to import the value.
static_stack.add_dependency(backend_stack)

app.synth()
