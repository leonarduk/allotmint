#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.backend_lambda_stack import BackendLambdaStack

app = cdk.App()
BackendLambdaStack(app, "BackendLambdaStack")
app.synth()
