import os
from collections.abc import Sequence
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    triggers,
)
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_authorizers
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from stacks.exports import BACKEND_API_URL_EXPORT


class BackendLambdaStack(Stack):
    """CDK stack that builds and deploys the backend Lambda."""

    @staticmethod
    def _lambda_log_group(scope: Construct, construct_id: str) -> logs.LogGroup:
        """Create the Lambda log group with the stack's standard retention policy."""

        return logs.LogGroup(
            scope,
            construct_id,
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

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

    @staticmethod
    def _grant_timeseries_cache_access(
        fn: _lambda.DockerImageFunction,
        *,
        bucket: s3.IBucket,
        allow_put: bool,
    ) -> None:
        """Grant S3 permissions required by the Lambda timeseries parquet cache.

        In AWS IAM, HeadObject is authorized by the s3:GetObject action (there
        is no separate s3:HeadObject action in the S3 IAM namespace), so a
        single s3:GetObject grant covers both parquet reads and cache-existence
        checks via boto3 head_object.
        """

        actions = ["s3:GetObject", "s3:HeadObject"]
        if allow_put:
            actions.append("s3:PutObject")

        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=actions,
                resources=[bucket.arn_for_objects("timeseries/*")],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": ["timeseries", "timeseries/*"]}},
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
            # alerts/ and prices/ are included because S3 returns 403 (not 404) when
            # a key is absent and the caller lacks s3:ListBucket on that prefix, which
            # prevents the fallback logic in alerts.py and the price-snapshot loader
            # from distinguishing "missing" from "denied". PriceRefreshLambda and
            # TradingAgentLambda also import the price loader during cold start.
            "backend": (
                "accounts",
                "alerts",
                "prices",
                "queries",
                "timeseries/meta",
                "transactions",
            ),
            # price_refresh needs accounts/ to call list_objects_v2 via
            # S3DataProvider.list_plots() → list_all_unique_tickers() → list_portfolios().
            # Without this ListBucket on accounts/, list_objects_v2 returns AccessDenied,
            # refresh_prices() finds no tickers, and the snapshot is never written.
            "price_refresh": ("accounts", "prices"),
            "trading_agent": ("prices",),
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

        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret:
            raise ValueError("JWT_SECRET must be set in the environment before deploying")
        google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        if not google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID must be set in the environment before deploying")

        backend_env = {
            "GOOGLE_AUTH_ENABLED": "true",
            # API Gateway enforces Cognito JWT auth before Lambda is invoked. DISABLE_AUTH
            # is intentionally "true" so FastAPI does not also try to decode the Cognito ID
            # token with the app JWT secret, which would reject every authenticated request.
            "DISABLE_AUTH": "true",
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            # APP_REGION is used instead of AWS_REGION because AWS_REGION is a reserved
            # Lambda runtime variable and cannot be set as a custom environment variable.
            "APP_REGION": self.region,
            "CORS_ORIGINS": ",".join(cors_origins),
            "JWT_SECRET": jwt_secret,
            "GOOGLE_CLIENT_ID": google_client_id,
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
        }
        if data_repo:
            backend_env["DATA_REPO"] = data_repo

        backend_log_group = self._lambda_log_group(self, "BackendLambdaLogGroup")
        backend_fn = _lambda.DockerImageFunction(
            self,
            "BackendLambda",
            code=image_code,
            environment=backend_env,
            log_group=backend_log_group,
            timeout=Duration.seconds(30),
            memory_size=512,
        )
        backend_fn.add_environment("APP_ENV", env)

        # BackendLambda: read + put + list for API data paths. Add an explicit
        # timeseries cache grant below so the synthesized IAM policy always covers
        # pyarrow's S3 parquet read/write/list behavior at timeseries/*.
        # Audited S3 list prefixes used by backend code paths:
        # - accounts/        (auth + portfolio enumeration)
        # - alerts/          (alert fallback path)
        # - prices/          (price snapshot loader)
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
        self._grant_timeseries_cache_access(backend_fn, bucket=data_bucket, allow_put=True)

        ui_auth_user_pool_id_default = self.node.try_get_context(
            "ui_auth_user_pool_id"
        ) or os.getenv("UI_AUTH_USER_POOL_ID")
        ui_auth_user_pool_id_param_kwargs = {
            "type": "String",
            "allowed_pattern": ".+",
            "description": (
                "Cognito user pool ID exported by StaticSiteStack for API JWT authorization."
            ),
        }
        if ui_auth_user_pool_id_default:
            ui_auth_user_pool_id_param_kwargs["default"] = ui_auth_user_pool_id_default
        ui_auth_user_pool_id_param = CfnParameter(
            self,
            "UiAuthUserPoolId",
            **ui_auth_user_pool_id_param_kwargs,
        )

        ui_auth_client_id_default = self.node.try_get_context(
            "ui_auth_user_pool_client_id"
        ) or os.getenv("UI_AUTH_USER_POOL_CLIENT_ID")
        ui_auth_client_id_param_kwargs = {
            "type": "String",
            "allowed_pattern": ".+",
            "description": (
                "Cognito app client ID exported by StaticSiteStack for API JWT authorization."
            ),
        }
        if ui_auth_client_id_default:
            ui_auth_client_id_param_kwargs["default"] = ui_auth_client_id_default
        ui_auth_client_id_param = CfnParameter(
            self,
            "UiAuthUserPoolClientId",
            **ui_auth_client_id_param_kwargs,
        )
        ui_auth_user_pool = cognito.UserPool.from_user_pool_id(
            self, "ImportedUiAuthUserPool", ui_auth_user_pool_id_param.value_as_string
        )
        backend_authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            "BackendCognitoAuthorizer",
            ui_auth_user_pool,
            user_pool_clients=[
                cognito.UserPoolClient.from_user_pool_client_id(
                    self, "ImportedUiAuthUserPoolClient", ui_auth_client_id_param.value_as_string
                )
            ],
            identity_source=["$request.header.Authorization"],
        )
        backend_api = apigwv2.HttpApi(
            self,
            "BackendApi",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["Authorization", "Content-Type", "X-CSRFToken"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_origins=cors_origins,
                allow_credentials=True,
            ),
        )
        self.backend_api_url = backend_api.api_endpoint
        backend_integration = apigwv2_integrations.HttpLambdaIntegration(
            "BackendLambdaIntegration", backend_fn
        )
        backend_api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=backend_integration,
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )
        # GET /config is the frontend's pre-auth bootstrap endpoint (see
        # frontend/src/main.tsx Root.fetchConfig / getConfig()): it must be
        # reachable before the caller has a Cognito token so the app can
        # determine whether auth is required at all. PUT /config (admin
        # config mutation) stays JWT-protected via the /{proxy+} catch-all.
        backend_api.add_routes(
            path="/config",
            methods=[apigwv2.HttpMethod.GET],
            integration=backend_integration,
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )
        backend_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.ANY],
            integration=backend_integration,
            authorizer=backend_authorizer,
        )
        backend_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=backend_integration,
            authorizer=backend_authorizer,
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
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
        }
        if data_repo:
            refresh_env["DATA_REPO"] = data_repo

        refresh_log_group = self._lambda_log_group(self, "PriceRefreshLambdaLogGroup")
        refresh_fn = _lambda.DockerImageFunction(
            self,
            "PriceRefreshLambda",
            code=refresh_code,
            environment=refresh_env,
            log_group=refresh_log_group,
            timeout=Duration.minutes(10),
            memory_size=512,
        )

        # PriceRefreshLambda: read + put by known data keys, plus scoped ListBucket
        # on prices/ so the price-snapshot loader can distinguish missing snapshots
        # from denied access during cold start. The explicit timeseries cache grant
        # also allows ListBucket on timeseries/ because some S3 parquet clients list
        # the prefix before reading or writing cached parquet files.
        # See backend/timeseries/cache.py:_rolling_cache() and _save_parquet().
        self._grant_bucket_access(
            refresh_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=True,
            allow_list=True,
            list_prefix=lambda_list_prefixes["price_refresh"],
        )
        self._grant_timeseries_cache_access(refresh_fn, bucket=data_bucket, allow_put=True)

        # Route all managed invocations through an explicit alias so Lambda
        # invoke permissions are qualified and remain compatible with AWS
        # authorization changes around Qualifier-based invocation.
        refresh_alias = _lambda.Alias(
            self,
            "PriceRefreshLambdaLiveAlias",
            alias_name="live",
            version=refresh_fn.current_version,
        )

        # Grant the CI deploy role permission to invoke the live alias so the
        # "Warm price snapshot" workflow step can call it after each deploy.
        # Dual-managed with bootstrap-deploy-role.sh (which bootstraps the role
        # before the first CDK deploy). This CDK grant re-applies on every
        # BackendLambdaStack deploy, keeping the permission current. See #3368.
        github_deploy_role_arn = os.getenv("GITHUB_DEPLOY_ROLE_ARN", "")
        if github_deploy_role_arn:
            # mutable=True is required: the role is bootstrapped externally
            # (bootstrap-deploy-role.sh) but CDK is the source of truth for
            # the inline policies attached below via add_to_principal_policy.
            # With mutable=False those calls would be no-ops and the grants
            # in this block would silently fail to apply. See #3370.
            github_role = iam.Role.from_role_arn(
                self, "GithubDeployRoleForLambdaInvoke", github_deploy_role_arn, mutable=True
            )
            refresh_alias.grant_invoke(github_role)

            # Grant the CI deploy role read access to the warmed price snapshot
            # so the "Warm price snapshot" workflow step's head-object check
            # succeeds. Mirrors the ReadPriceSnapshot/ListPricesPrefix
            # statements in bootstrap-deploy-role.sh (used only to bootstrap
            # the role before the first CDK deploy); this CDK grant is the
            # source of truth thereafter and re-applies on every
            # BackendLambdaStack deploy, preventing drift. See #3191, #3639.
            github_role.add_to_principal_policy(
                iam.PolicyStatement(
                    sid="ReadPriceSnapshot",
                    actions=["s3:GetObject"],
                    resources=[data_bucket.arn_for_objects("prices/latest_prices.json")],
                )
            )
            github_role.add_to_principal_policy(
                iam.PolicyStatement(
                    sid="ListPricesPrefix",
                    actions=["s3:ListBucket"],
                    resources=[data_bucket.bucket_arn],
                    conditions={"StringLike": {"s3:prefix": ["prices", "prices/*"]}},
                )
            )

            # Grant the CI deploy role read access to BackendLambda's CloudWatch
            # logs so the "Fetch BackendLambda CloudWatch logs" deploy steps can
            # surface post-deploy errors instead of silently swallowing
            # AccessDeniedException. Mirrors the FilterLogEvents statement in
            # bootstrap-deploy-role.sh; this CDK grant is the source of truth
            # thereafter and re-applies on every BackendLambdaStack deploy,
            # preventing drift. See #3742.
            # logs:DescribeLogStreams is also granted, following the
            # ReadPriceSnapshot/ListPricesPrefix pattern from #3191, so log
            # inspection tooling can enumerate the BackendLambda log streams
            # without an AccessDeniedException. See #3768.
            github_role.add_to_principal_policy(
                iam.PolicyStatement(
                    sid="FilterBackendLambdaLogEvents",
                    actions=["logs:FilterLogEvents", "logs:DescribeLogStreams"],
                    resources=[backend_log_group.log_group_arn],
                )
            )

        events.Rule(
            self,
            "DailyPriceRefresh",
            schedule=events.Schedule.cron(minute="0", hour="0"),
            targets=[targets.LambdaFunction(refresh_alias)],
        )

        # Invoke PriceRefreshLambda synchronously after each deployment so
        # prices/latest_prices.json is seeded in S3 before the smoke tests run.
        # REQUEST_RESPONSE blocks the CDK deploy until the Lambda finishes,
        # guaranteeing the snapshot is present by the time the smoke-test job
        # starts. The Trigger timeout (15 min) must be strictly greater than
        # refresh_fn.timeout (10 min) so the custom resource provider can wait
        # for the Lambda response before CloudFormation signals completion.
        #
        # NOTE: the Lambda handler catches all exceptions and writes an empty stub
        # snapshot on failure rather than raising, so a transient API outage does
        # not roll back the entire CloudFormation stack (which would happen if the
        # Lambda returned an error to the REQUEST_RESPONSE Trigger). The stub is
        # overwritten by the next successful scheduled EventBridge invocation.
        triggers.Trigger(
            self,
            "PriceRefreshOnDeploy",
            handler=refresh_fn,
            invocation_type=triggers.InvocationType.REQUEST_RESPONSE,
            timeout=Duration.minutes(15),
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
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
        }
        if data_repo:
            agent_env["DATA_REPO"] = data_repo

        agent_log_group = self._lambda_log_group(self, "TradingAgentLambdaLogGroup")
        agent_fn = _lambda.DockerImageFunction(
            self,
            "TradingAgentLambda",
            code=agent_code,
            environment=agent_env,
            log_group=agent_log_group,
        )

        # TradingAgentLambda: read-only, no put, no general list. It has scoped
        # ListBucket on prices/ so the price-snapshot loader can distinguish missing
        # snapshots from denied access during cold start.
        # Audited: trading_agent.py:run() → load_prices_for_tickers()
        # → load_meta_timeseries_range() reads parquet from S3 by known key.
        # No S3 writes: _log_trade() writes to TRADE_LOG_PATH (local filesystem / CloudWatch).
        # The timeseries cache grant adds scoped GetObject and ListBucket so pyarrow
        # can read cached parquet files under timeseries/. allow_put=False enforces
        # the read-only invariant on the timeseries prefix.
        self._grant_bucket_access(
            agent_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=False,
            allow_list=True,
            list_prefix=lambda_list_prefixes["trading_agent"],
        )
        self._grant_timeseries_cache_access(agent_fn, bucket=data_bucket, allow_put=False)

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
        CfnOutput(self, "BackendLambdaLogGroupName", value=backend_log_group.log_group_name)
        CfnOutput(self, "PriceRefreshLambdaLogGroupName", value=refresh_log_group.log_group_name)
        CfnOutput(self, "TradingAgentLambdaLogGroupName", value=agent_log_group.log_group_name)
        CfnOutput(self, "BackendLambdaErrorAlarmName", value=backend_error_alarm.alarm_name)
