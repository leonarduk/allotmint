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
        data_repo = os.getenv("DATA_REPO")
        data_branch = os.getenv("DATA_BRANCH", "main")
        bucket_name = self.node.try_get_context("data_bucket") or os.getenv("DATA_BUCKET")
        if not bucket_name:
            raise ValueError(
                "DATA_BUCKET must be provided via context or DATA_BUCKET environment variable",
            )
        build_args: dict[str, str] = {
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
        }
        if data_repo:
            build_args["DATA_REPO"] = data_repo

        image_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root), file="backend/Dockerfile.lambda", build_args=build_args
        )

        env = self.node.try_get_context("app_env") or os.getenv("APP_ENV") or "aws"

        backend_env = {
            "GOOGLE_AUTH_ENABLED": "true",
            "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
            "DISABLE_AUTH": "false",
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
        }
        if data_repo:
            backend_env["DATA_REPO"] = data_repo

        backend_fn = _lambda.DockerImageFunction(
            self,
            "BackendLambda",
            code=image_code,
            environment=backend_env,
        )
        backend_fn.add_environment("APP_ENV", env)

        apigw.LambdaRestApi(self, "BackendApi", handler=backend_fn)

        # Scheduled function to refresh prices daily
        refresh_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root),
            file="backend/Dockerfile.lambda",
            cmd=["backend.lambda_api.price_refresh.lambda_handler"],
            build_args=build_args,
        )
        refresh_env = {
            "APP_ENV": env,
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
        }
        if data_repo:
            refresh_env["DATA_REPO"] = data_repo

        refresh_fn = _lambda.DockerImageFunction(
            self,
            "PriceRefreshLambda",
            code=refresh_code,
            environment=refresh_env,
        )

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_fn)],
        )
