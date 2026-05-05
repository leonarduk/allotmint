import os
from collections.abc import Sequence
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from stacks.exports import BACKEND_API_URL_EXPORT


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    @staticmethod
    def _grant_bucket_access(
        fn: _lambda.DockerImageFunction,
        *,
        bucket: s3.IBucket | None = None,
        bucket_name: str | None = None,
        allow_read: bool,
        allow_put: bool,
        allow_list: bool,
        list_prefix: str | Sequence[str] | None = None,
    ) -> None:
        """Grant the minimum required S3 actions for a Lambda function.

        Accepts either a CDK ``bucket`` construct or a plain ``bucket_name`` string
        (useful in unit tests that don't synthesise a full stack).

        ``allow_list`` controls ``s3:ListBucket`` on the bucket ARN while
        ``allow_read``/``allow_put`` scope object-level actions to ``/*``.
        """

        if bucket is None and bucket_name is None:
            raise ValueError("Provide either bucket or bucket_name")
        if bucket is not None and bucket_name is not None:
            raise ValueError("Provide either bucket or bucket_name, not both")

        if not any((allow_read, allow_put, allow_list)):
            raise ValueError(
                "_grant_bucket_access called with no permissions enabled — this is a no-op. "
                "Pass at least one of allow_read, allow_put, or allow_list as True."
            )

        if bucket is not None:
            object_arn: str = bucket.arn_for_objects("*")
            bucket_arn: str = bucket.bucket_arn
        else:
            object_arn = f"arn:aws:s3:::{bucket_name}/*"
            bucket_arn = f"arn:aws:s3:::{bucket_name}"

        object_actions: list[str] = []
        if allow_read:
            object_actions.append("s3:GetObject")
        if allow_put:
            object_actions.append("s3:PutObject")

        if object_actions:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=object_actions,
                    resources=[object_arn],
                )
            )

        if allow_list:
            raw_prefixes: list[str]
            if isinstance(list_prefix, str):
                raw_prefixes = [list_prefix]
            elif list_prefix is None:
                raw_prefixes = []
            else:
                raw_prefixes = list(list_prefix)

            normalized_prefixes = [prefix.strip().strip("/") for prefix in raw_prefixes]
            normalized_prefixes = [prefix for prefix in normalized_prefixes if prefix]
            if not normalized_prefixes:
                raise ValueError("list_prefix is required when allow_list=True")

            prefix_conditions: list[str] = []
            for prefix in normalized_prefixes:
                prefix_conditions.append(prefix)
                prefix_conditions.append(f"{prefix}/*")
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[bucket_arn],
                    conditions={"StringLike": {"s3:prefix": prefix_conditions}},
                )
            )

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_root = Path(__file__).resolve().parents[2]

        data_repo = os.getenv("DATA_REPO")
        data_branch = os.getenv("DATA_BRANCH", "main")
        budget_limit_usd = float(
            self.node.try_get_context("monthly_budget_limit_usd")
            or os.getenv("MONTHLY_BUDGET_LIMIT_USD", "5")
        )
        noncurrent_expiry_days = int(
            self.node.try_get_context("data_bucket_noncurrent_expiry_days")
            or os.getenv("DATA_BUCKET_NONCURRENT_EXPIRY_DAYS", "30")
        )
        budget_alert_email = self.node.try_get_context("budget_alert_email") or os.getenv(
            "BUDGET_ALERT_EMAIL"
        )
        secret_name = self.node.try_get_context("app_secret_name") or os.getenv(
            "APP_SECRET_NAME", "allotmint/app"
        )

        app_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "AppConfigSecret", secret_name
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
        lambda_list_prefixes = {
            "backend": ("accounts", "queries", "timeseries/meta", "transactions"),
            "price_refresh": (),
            "trading_agent": (),
        }

        image_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root), file="backend/Dockerfile.lambda"
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
            "DISABLE_AUTH": "false",
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            # APP_REGION is used instead of AWS_REGION because AWS_REGION is a reserved
            # Lambda runtime variable and cannot be set as a custom environment variable.
            "APP_REGION": self.region,
            "CORS_ORIGINS": ",".join(cors_origins),
            # The secret name is passed explicitly so load_aws_secrets_to_env() can
            # retrieve JWT_SECRET and GOOGLE_CLIENT_ID at Lambda cold-start.
            "APP_SECRET_NAME": secret_name,
        }
        if data_repo:
            backend_env["DATA_REPO"] = data_repo

        backend_fn = _lambda.DockerImageFunction(
            self,
            "BackendLambda",
            code=image_code,
            environment=backend_env,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        backend_fn.add_environment("APP_ENV", env)
        app_secret.grant_read(backend_fn)

        # BackendLambda: read + put + list
        # Audited S3 list prefixes used by backend code paths:
        # - accounts/        (auth + portfolio enumeration)
        # - queries/         (saved query listing)
        # - timeseries/meta/ (timeseries admin listing)
        # - transactions/    (report transaction exports)
        self._grant_bucket_access(
            backend_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=True,
            allow_list=True,
            list_prefix=lambda_list_prefixes["backend"],
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
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        app_secret.grant_read(refresh_fn)

        # PriceRefreshLambda: read + put, no list
        # Audited: refresh_prices() calls get_price_snapshot() → load_meta_timeseries_range()
        # → _rolling_cache() → _save_parquet(), which writes parquet files to S3 by known key
        # (e.g. s3://bucket/meta/TICKER_EXCHANGE.parquet). All S3 access is by known key —
        # no bucket enumeration. config.prices_json writes to local filesystem, not S3.
        # See backend/timeseries/cache.py:_rolling_cache() and _save_parquet().
        self._grant_bucket_access(
            refresh_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=True,
            allow_list=False,
            list_prefix=lambda_list_prefixes["price_refresh"],
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
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        app_secret.grant_read(agent_fn)

        # TradingAgentLambda: read only, no put, no list
        # Audited: backend/agent/trading_agent.py:run() calls load_prices_for_tickers()
        # → load_meta_timeseries_range() which reads parquet files from S3 by known key.
        # No S3 writes: _log_trade() writes to TRADE_LOG_PATH (local filesystem / CloudWatch).
        # No bucket enumeration: all S3 access is by deterministic key.
        self._grant_bucket_access(
            agent_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=False,
            allow_list=False,
            list_prefix=lambda_list_prefixes["trading_agent"],
        )

        events.Rule(
            self,
            "DailyTradingAgentRun",
            schedule=events.Schedule.cron(minute="0", hour="1"),
            targets=[targets.LambdaFunction(agent_fn)],
        )

        # IAM implicit deny covers all other principals; no explicit DENY
        # resource policy is needed (and a StringNotLike list-based DENY
        # would incorrectly lock out these roles too).

        backend_error_alarm = cloudwatch.Alarm(
            self,
            "BackendLambdaErrorAlarm",
            metric=backend_fn.metric_errors(period=Duration.minutes(5)),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        budget_notification = None
        if budget_alert_email:
            budget_notification = budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(
                    notification_type="ACTUAL",
                    comparison_operator="GREATER_THAN",
                    threshold=80,
                    threshold_type="PERCENTAGE",
                ),
                subscribers=[
                    budgets.CfnBudget.SubscriberProperty(
                        subscription_type="EMAIL", address=budget_alert_email
                    )
                ],
            )

        budgets.CfnBudget(
            self,
            "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=budget_limit_usd,
                    unit="USD",
                ),
                time_unit="MONTHLY",
                budget_name=f"{self.stack_name}-monthly-budget",
            ),
            notifications_with_subscribers=[budget_notification] if budget_notification else None,
        )

        CfnOutput(
            self,
            "BackendApiUrl",
            value=backend_api.api_endpoint,
            export_name=BACKEND_API_URL_EXPORT,
        )
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "BackendLambdaErrorAlarmName", value=backend_error_alarm.alarm_name)
