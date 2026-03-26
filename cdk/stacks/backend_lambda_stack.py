import os
from pathlib import Path

from aws_cdk import (
    Stack,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
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
        frontend_origin = self.node.try_get_context("frontend_origin") or os.getenv(
            "FRONTEND_ORIGIN"
        )
        extra_cors_origins = self.node.try_get_context("cors_origins") or os.getenv(
            "CORS_ORIGINS"
        )

        cors_origins = ["http://localhost:3000", "http://localhost:5173"]
        if frontend_origin:
            cors_origins.insert(0, frontend_origin)
        if extra_cors_origins:
            cors_origins.extend(
                [origin.strip() for origin in extra_cors_origins.split(",") if origin.strip()]
            )
        cors_origins = list(dict.fromkeys(cors_origins))

        backend_env = {
            "GOOGLE_AUTH_ENABLED": "true",
            "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
            "DISABLE_AUTH": "false",
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            "AWS_REGION": self.region,
            "CORS_ORIGINS": ",".join(cors_origins),
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

        backend_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[f"arn:aws:s3:::{bucket_name}/*"],
            )
        )

        backend_api = apigwv2.HttpApi(self, "BackendApi")
        backend_integration = apigwv2_integrations.HttpLambdaIntegration(
            "BackendLambdaIntegration", backend_fn
        )
        backend_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.ANY],
            integration=backend_integration,
        )
        backend_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=backend_integration,
        )

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

        # Scheduled function to execute the trading agent
        agent_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root),
            file="backend/Dockerfile.lambda",
            cmd=["backend.lambda_api.trading_agent.lambda_handler"],
            build_args=build_args,
        )
        agent_env = {
            "APP_ENV": env,
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
        }
        if data_repo:
            agent_env["DATA_REPO"] = data_repo

        agent_fn = _lambda.DockerImageFunction(
            self,
            "TradingAgentLambda",
            code=agent_code,
            environment=agent_env,
        )

        events.Rule(
            self,
            "DailyTradingAgentRun",
            schedule=events.Schedule.cron(minute="0", hour="1"),
            targets=[targets.LambdaFunction(agent_fn)],
        )
