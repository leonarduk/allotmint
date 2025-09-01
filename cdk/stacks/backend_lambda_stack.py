import os
from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]
        backend_path = project_root / "backend"

        dependencies_layer = _lambda.LayerVersion(
            self,
            "BackendDependencies",
            code=_lambda.Code.from_asset(
                str(backend_path),
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements-lambda.txt -t /asset-output/python",
                    ],
                ),
            ),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        )

        backend_code = _lambda.Code.from_asset(str(backend_path))

        bucket_name = self.node.try_get_context("data_bucket") or os.getenv("DATA_BUCKET")
        if not bucket_name:
            raise ValueError(
                "DATA_BUCKET must be provided via context or DATA_BUCKET environment variable",
            )
        env = self.node.try_get_context("app_env") or os.getenv("APP_ENV") or "aws"

        backend_fn = _lambda.Function(
            self,
            "BackendLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.lambda_api.handler.lambda_handler",
            code=backend_code,
            layers=[dependencies_layer],
            environment={
                "GOOGLE_AUTH_ENABLED": "true",
                "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
                "ALLOWED_EMAILS": "${ALLOWED_EMAILS}",
            },
        )
        backend_fn.add_environment("APP_ENV", env)
        backend_fn.add_environment("DATA_BUCKET", bucket_name)

        if env == "production":
            backend_fn.add_environment("GOOGLE_AUTH_ENABLED", "true")
            backend_fn.add_environment("DISABLE_AUTH", "false")

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)

        # Scheduled function to refresh prices daily
        refresh_fn = _lambda.Function(
            self,
            "PriceRefreshLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.lambda_api.price_refresh.lambda_handler",
            code=backend_code,
            layers=[dependencies_layer],
        )
        refresh_fn.add_environment("APP_ENV", env)
        refresh_fn.add_environment("DATA_BUCKET", bucket_name)

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_fn)],
        )
