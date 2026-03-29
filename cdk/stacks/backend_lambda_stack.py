import os
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    @staticmethod
    def _grant_bucket_access(
        fn: _lambda.DockerImageFunction,
        *,
        bucket_name: str,
        allow_read: bool,
        allow_put: bool,
        allow_list: bool,
    ) -> None:
        """Grant the minimum required S3 actions for a Lambda function.

        ``allow_list`` controls ``s3:ListBucket`` on the bucket ARN while
        ``allow_read``/``allow_put`` scope object-level actions to ``/*``.
        """

        object_actions: list[str] = []
        if allow_read:
            object_actions.append("s3:GetObject")
        if allow_put:
            object_actions.append("s3:PutObject")

        if object_actions:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=object_actions,
                    resources=[f"arn:aws:s3:::{bucket_name}/*"],
                )
            )

        if allow_list:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[f"arn:aws:s3:::{bucket_name}"],
                )
            )

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]

        data_repo = os.getenv("DATA_REPO")
        data_branch = os.getenv("DATA_BRANCH", "main")
        noncurrent_expiry_days = int(
            self.node.try_get_context("data_bucket_noncurrent_expiry_days")
            or os.getenv("DATA_BUCKET_NONCURRENT_EXPIRY_DAYS", "30")
        )

        data_bucket = s3.Bucket(
            self,
            "PortfolioDataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    noncurrent_version_expiration=Duration.days(noncurrent_expiry_days)
                )
            ],
        )

        bucket_name = data_bucket.bucket_name

        seed_data_bucket = (
            self.node.try_get_context("seed_data_bucket")
            or os.getenv("SEED_DATA_BUCKET")
            or os.getenv("DATA_BUCKET")
        )
        build_args: dict[str, str] = {
            "DATA_BUCKET": seed_data_bucket or "",
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
        extra_cors_origins = self.node.try_get_context("cors_origins") or os.getenv("CORS_ORIGINS")

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
            # APP_REGION is used instead of AWS_REGION because AWS_REGION is a reserved
            # Lambda runtime variable and cannot be set as a custom environment variable.
            "APP_REGION": self.region,
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

        # BackendLambda: read + put + list
        # Audited: serves API requests that read and write portfolio/price data to S3.
        self._grant_bucket_access(
            backend_fn,
            bucket_name=bucket_name,
            allow_read=True,
            allow_put=True,
            allow_list=True,
        )

        backend_api = apigwv2.HttpApi(self, "BackendApi")
        self.backend_api_url = backend_api.api_endpoint
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

        # PriceRefreshLambda: read + list only (no put)
        # Audited: refresh_prices() writes prices_json to local filesystem path (config.prices_json
        # resolves under data_root on disk), not to S3. S3 access is read-only for price history.
        self._grant_bucket_access(
            refresh_fn,
            bucket_name=bucket_name,
            allow_read=True,
            allow_put=False,
            allow_list=True,
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

        # TradingAgentLambda: read + list only (no put)
        # Audited: backend/agent/trading_agent.py calls load_prices_for_tickers() (S3 read)
        # and _log_trade() which writes to TRADE_LOG_PATH (local filesystem). No S3 writes.
        self._grant_bucket_access(
            agent_fn,
            bucket_name=bucket_name,
            allow_read=True,
            allow_put=False,
            allow_list=True,
        )

        events.Rule(
            self,
            "DailyTradingAgentRun",
            schedule=events.Schedule.cron(minute="0", hour="1"),
            targets=[targets.LambdaFunction(agent_fn)],
        )

        CfnOutput(self, "BackendApiUrl", value=backend_api.api_endpoint)
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
