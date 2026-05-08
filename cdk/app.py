#!/usr/bin/env python3

import aws_cdk as cdk
from stacks.backend_lambda_stack import BackendLambdaStack
from stacks.static_site_stack import StaticSiteStack

app = cdk.App()

# Always include both stacks. StaticSiteStack owns the Cognito hosted UI and
# exports the user-pool identifiers. BackendLambdaStack consumes those values
# through deploy-time parameters so API Gateway can enforce Cognito JWTs without
# creating a CloudFormation import/dependency cycle.
backend_stack = BackendLambdaStack(app, "BackendLambdaStack")

# StaticSiteStack uses a CfnParameter (BackendApiUrl) for the backend URL so
# that BucketDeployment.Source.json_data() receives an intra-stack Ref token —
# the only kind its renderData validator accepts. The real URL is injected at
# deploy time via:
#   cdk deploy StaticSiteStack --parameters StaticSiteStack:BackendApiUrl=<url>
# See deploy-lambda.yml for the two-phase static/backend/static deployment that
# first creates Cognito, then wires API authorization, then refreshes config.json.
static_stack = StaticSiteStack(app, "StaticSiteStack")

app.synth()
