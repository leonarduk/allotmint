#!/usr/bin/env python3

import aws_cdk as cdk

from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.static_site_stack import StaticSiteStack

app = cdk.App()

# Always include the backend stack so it can be deployed without
# providing a context flag or environment variable.
backend_stack = BackendLambdaStack(app, "BackendLambdaStack")

# StaticSiteStack uses a CfnParameter (BackendApiUrl) for the backend URL so
# that BucketDeployment.Source.json_data() receives an intra-stack Ref token —
# the only kind its renderData validator accepts.  The real URL is injected at
# deploy time via:
#   cdk deploy StaticSiteStack --parameters StaticSiteStack:BackendApiUrl=<url>
# See deploy-lambda.yml for how the URL is extracted from BackendLambdaStack.
static_stack = StaticSiteStack(app, "StaticSiteStack")
# Deployment order is managed explicitly by deploy-lambda.yml:
# 1. StaticSiteStack → creates Cognito User Pool, exposes UiAuthUserPoolId / UiAuthUserPoolClientId
# 2. BackendLambdaStack → uses those IDs as CfnParameters, exposes BackendApiUrl
# 3. StaticSiteStack (redeploy) → injects BackendApiUrl into the runtime config
# A CDK add_dependency here would force BackendLambdaStack to deploy before
# StaticSiteStack, which is the opposite of the required order and causes the
# CfnParameters to have no value on the first run.

app.synth()
