#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.static_site_stack import StaticSiteStack


app = cdk.App()

# Always include the backend stack so it can be deployed without
# providing a context flag or environment variable.
BackendLambdaStack(app, "BackendLambdaStack")

StaticSiteStack(app, "StaticSiteStack")

app.synth()
