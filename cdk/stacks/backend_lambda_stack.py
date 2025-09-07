import os
from pathlib import Path

from aws_cdk import (
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

        # Build a Docker image for the Lambda runtime to avoid large zip/layer sizes
        image_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root / "backend"), file="Dockerfile.lambda"
        )

        bucket_name = self.node.try_get_context("data_bucket") or os.getenv("DATA_BUCKET")
        if not bucket_name:
            raise ValueError(
                "DATA_BUCKET must be provided via context or DATA_BUCKET environment variable",
            )
        env = self.node.try_get_context("app_env") or os.getenv("APP_ENV") or "aws"

        backend_fn = _lambda.DockerImageFunction(
            self,
            "BackendLambda",
            code=image_code,
            environment={
                "GOOGLE_AUTH_ENABLED": "true",
                "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
                "DISABLE_AUTH": "false",
            },
        )
        backend_fn.add_environment("APP_ENV", env)
        backend_fn.add_environment("DATA_BUCKET", bucket_name)

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)

        # Scheduled function to refresh prices daily
        refresh_fn = _lambda.DockerImageFunction(
            self,
            "PriceRefreshLambda",
            code=_lambda.DockerImageCode.from_image_asset(
                str(project_root / "backend"),
                file="Dockerfile.lambda",
                cmd=["backend.lambda_api.price_refresh.lambda_handler"],
            ),
        )
        refresh_fn.add_environment("APP_ENV", env)
        refresh_fn.add_environment("DATA_BUCKET", bucket_name)

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_fn)],
        )
