import os
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

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
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        backend_fn.add_environment("APP_ENV", env)
        app_secret.grant_read(backend_fn)

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
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        app_secret.grant_read(refresh_fn)

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
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        app_secret.grant_read(agent_fn)

        events.Rule(
            self,
            "DailyTradingAgentRun",
            schedule=events.Schedule.cron(minute="0", hour="1"),
            targets=[targets.LambdaFunction(agent_fn)],
        )

        # Grant Lambda roles read/write on the data bucket.
        # IAM implicit deny covers all other principals; no explicit DENY
        # resource policy is needed (and a StringNotLike list-based DENY
        # would incorrectly lock out these roles too).
        lambda_roles = [backend_fn.role, refresh_fn.role, agent_fn.role]
        for role in lambda_roles:
            if role is None:
                continue
            data_bucket.grant_read_write(role)

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

        CfnOutput(self, "BackendApiUrl", value=backend_api.api_endpoint)
        CfnOutput(self, "DataBucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "BackendLambdaErrorAlarmName", value=backend_error_alarm.alarm_name)
