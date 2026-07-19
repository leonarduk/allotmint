import json
import os
from collections.abc import Sequence
from pathlib import Path

from aws_cdk import (
    CfnCondition,
    CfnOutput,
    CfnParameter,
    Duration,
    Fn,
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

# S3 prefix (relative to the data bucket) under which per-owner writable account
# documents are persisted. Kept in sync with
# ``backend.common.accounts_store.WRITABLE_ACCOUNTS_PREFIX`` via the
# ``WRITABLE_ACCOUNTS_PREFIX`` Lambda environment variable below. Deliberately
# distinct from the read-only ``accounts/`` demo prefix (issue #4275).
WRITABLE_ACCOUNTS_PREFIX = "writable-accounts"

# S3 prefix (relative to the data bucket) under which auto-created instrument
# metadata is persisted when the local filesystem is read-only (Lambda).
# Kept in sync with the default in
# ``backend.common.instruments._s3_location()`` via the ``METADATA_PREFIX``
# Lambda environment variable below (issue #4930).
METADATA_PREFIX = "instruments"

# API Gateway access-log format for the backend HTTP API's default stage.
# Deliberately logs claims/status/source IP only — never the raw bearer
# token or Authorization header — so no credentials land in the logs.
# Applied to the default stage in BackendLambdaStack.__init__ (issue #4255, #4738).
ACCESS_LOG_FORMAT = json.dumps(
    {
        "requestId": "$context.requestId",
        "routeKey": "$context.routeKey",
        "status": "$context.status",
        "errorMessage": "$context.error.message",
        "authorizerError": "$context.authorizer.error",
        "integrationStatus": "$context.integrationStatus",
        "responseLatency": "$context.responseLatency",
        "sourceIp": "$context.identity.sourceIp",
    }
)


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
        put_prefix: str | Sequence[str] | None = None,
    ) -> None:
        """Grant the minimum required S3 actions for a Lambda function.

        Accepts either a CDK ``bucket`` construct or a plain ``bucket_name`` string
        (useful in unit tests that don't synthesise a full stack).

        ``allow_list`` controls ``s3:ListBucket`` on the bucket ARN while
        ``allow_read`` scopes ``s3:GetObject`` to ``/*``. ``allow_put`` scopes
        ``s3:PutObject`` to ``/*`` by default; pass ``put_prefix`` to instead
        scope the write grant to specific prefix(es) (e.g. the Lambda's own
        snapshot path) for least privilege. ``put_prefix`` is independent of
        ``list_prefix`` — a caller may need to list one set of prefixes but
        write only to a narrower one (issue #5013).
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

        if allow_read:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject"],
                    resources=[object_arn],
                )
            )

        if allow_put:
            if put_prefix is not None:
                raw_put_prefixes = [put_prefix] if isinstance(put_prefix, str) else list(put_prefix)
                normalized_put_prefixes = [prefix.strip().strip("/") for prefix in raw_put_prefixes]
                normalized_put_prefixes = [prefix for prefix in normalized_put_prefixes if prefix]
                if not normalized_put_prefixes:
                    raise ValueError("put_prefix, if provided, must contain a non-empty prefix")
                if bucket is not None:
                    put_resources = [
                        bucket.arn_for_objects(f"{prefix}/*") for prefix in normalized_put_prefixes
                    ]
                else:
                    put_resources = [
                        f"arn:aws:s3:::{bucket_name}/{prefix}/*"
                        for prefix in normalized_put_prefixes
                    ]
            else:
                put_resources = [object_arn]
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:PutObject"],
                    resources=put_resources,
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
    def _require_single_cfn_authorizer(
        cfn_authorizers: Sequence[apigwv2.CfnAuthorizer],
    ) -> apigwv2.CfnAuthorizer:
        """Return the sole entry in ``cfn_authorizers`` or raise ``ValueError``.

        Guards against silently overriding the wrong resource if a second
        authorizer is ever added to backend_api (#4057).
        """

        if len(cfn_authorizers) != 1:
            raise ValueError(
                "Expected exactly one CfnAuthorizer under BackendApi, found "
                f"{len(cfn_authorizers)}"
            )
        return cfn_authorizers[0]

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
        # Public account-signup request flow (#4352, #5367). These vars must be
        # set for the create-account form and admin approval email flow to work.
        # Supplied via CDK context or env var rather than hardcoded in the stack.
        signup_admin_email = self.node.try_get_context("signup_admin_email") or os.getenv(
            "SIGNUP_ADMIN_EMAIL", ""
        )
        signup_approval_base_url = self.node.try_get_context("signup_approval_base_url") or os.getenv(
            "SIGNUP_APPROVAL_BASE_URL", ""
        )
        signup_login_url = self.node.try_get_context("signup_login_url") or os.getenv(
            "SIGNUP_LOGIN_URL", ""
        )
        # Cadence for the pension report Lambda's EventBridge rule (issue #2758).
        # "weekly" -> every Monday; "monthly" -> the 1st of the month. Configurable
        # via CDK context or env var rather than hardcoded in the rule itself.
        pension_report_cadence = (
            self.node.try_get_context("pension_report_cadence")
            or os.getenv("PENSION_REPORT_CADENCE")
            or "weekly"
        )
        if pension_report_cadence not in {"weekly", "monthly"}:
            raise ValueError(
                "pension_report_cadence must be 'weekly' or 'monthly', got "
                f"{pension_report_cadence!r}"
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
            # alerts/, prices/, and instruments/ are included because S3 returns 403
            # (not 404) when a key is absent and the caller lacks s3:ListBucket on
            # that prefix, which prevents the fallback logic in alerts.py, the
            # price-snapshot loader, and instruments.py from distinguishing "missing"
            # from "denied". Without ListBucket on instruments/, every metadata lookup
            # for a ticker not already cached locally falls back to a live Yahoo
            # Finance call plus a failed local write (the Lambda filesystem is
            # read-only), which is slow enough per-ticker to time out the whole
            # request once repeated across a portfolio's instruments (issue #5015).
            # PriceRefreshLambda and TradingAgentLambda also import the price loader
            # during cold start.
            "backend": (
                "accounts",
                "alerts",
                "instruments",
                "prices",
                "queries",
                "timeseries/meta",
                "transactions",
                # Writable, per-owner account documents (manual holdings and
                # transaction writes) live under a dedicated prefix that is
                # separate from the read-only ``accounts/`` demo dataset so
                # writes never mutate shared data (issue #4275). ListBucket on
                # this prefix is required by AccountsStore list/iter paths;
                # object-level Get/Put are already granted bucket-wide below.
                WRITABLE_ACCOUNTS_PREFIX,
            ),
            # price_refresh needs accounts/ to call list_objects_v2 via
            # S3DataProvider.list_plots() → list_all_unique_tickers() → list_portfolios().
            # Without this ListBucket on accounts/, list_objects_v2 returns AccessDenied,
            # refresh_prices() finds no tickers, and the snapshot is never written.
            "price_refresh": ("accounts", "prices"),
            "trading_agent": ("prices",),
            # dividend_refresh reads holdings/transactions via AccountsStore
            # (iter_transaction_documents() → ListBucket on writable-accounts/)
            # and writes new DIVIDEND transactions back to the same prefix.
            # See backend/common/dividends.py::refresh_dividends() (issue #2750).
            "dividend_refresh": (WRITABLE_ACCOUNTS_PREFIX,),
            # pension_report calls list_portfolios() -> list_plots(), which needs
            # ListBucket on accounts/ for the same reason as price_refresh above
            # (issue #2758).
            "pension_report": ("accounts",),
        }

        image_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root), file="backend/Dockerfile.lambda"
        )

        env = self.node.try_get_context("app_env") or os.getenv("APP_ENV") or "aws"
        # Per-deploy override (e.g. a preview environment's own frontend URL),
        # supplied via CDK context or env var. Inserted at position 0 below so
        # it takes priority when dict.fromkeys() dedupes the final list.
        frontend_origin = self.node.try_get_context("frontend_origin") or os.getenv(
            "FRONTEND_ORIGIN"
        )
        # Operator-supplied additional origins (comma-separated), for cases the
        # base list + frontend_origin don't cover — e.g. a temporary staging
        # domain. Supplied via CDK context or the CORS_ORIGINS env var.
        extra_cors_origins = self.node.try_get_context("cors_origins") or os.getenv("CORS_ORIGINS")

        cors_origins = [
            # Vite dev server default port. Always present so `npm run dev`
            # works against a deployed backend without extra config.
            "http://localhost:3000",
            # CRA-style / alternate local dev server port, kept for the same
            # reason as above. Both localhost entries are dev-only convenience:
            # they're baked in at synth time and only ever reach a deployed
            # stack if a developer points their local frontend at it, so they
            # are not normalised or rejected for non-local environments here
            # (audit for #4113 — no change needed).
            "http://localhost:5173",
            # Production frontend. Remove only if app.allotmint.io stops being
            # the production domain.
            "https://app.allotmint.io",
        ]
        if frontend_origin:
            cors_origins.insert(0, frontend_origin)
        if extra_cors_origins:
            cors_origins.extend(
                [origin.strip() for origin in extra_cors_origins.split(",") if origin.strip()]
            )
        cors_origins = list(dict.fromkeys(cors_origins))

        # Deliberately always-required (not routed through stacks.prod_env's
        # assert_prod_env_vars), unlike GITHUB_DEPLOY_ROLE_ARN in
        # StaticSiteStack: these two are needed for the Lambda to function in
        # every environment, including local/dev synths, not just prod. See
        # #4731.
        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret:
            raise ValueError("JWT_SECRET must be set in the environment before deploying")
        google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        if not google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID must be set in the environment before deploying")

        backend_env = {
            "GOOGLE_AUTH_ENABLED": "true",
            # API Gateway enforces Cognito JWT auth before Lambda is invoked, so the
            # Lambda must not attempt its own JWT decode (DISABLE_AUTH="true"). Auth is
            # still enforced — API Gateway rejects unauthenticated requests before they
            # reach Lambda.
            "DISABLE_AUTH": "true",
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            # Writable per-owner account documents are persisted under this S3
            # prefix, separate from the read-only accounts/ demo data (#4275).
            "WRITABLE_ACCOUNTS_PREFIX": WRITABLE_ACCOUNTS_PREFIX,
            # APP_REGION is used instead of AWS_REGION because AWS_REGION is a reserved
            # Lambda runtime variable and cannot be set as a custom environment variable.
            "APP_REGION": self.region,
            "CORS_ORIGINS": ",".join(cors_origins),
            "JWT_SECRET": jwt_secret,
            "GOOGLE_CLIENT_ID": google_client_id,
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
            # Without this, backend.common.instruments._s3_location() returns
            # None and auto-created instrument metadata falls back to writing
            # under /var/task, which is read-only in Lambda (issue #4930).
            # Shares the existing data bucket/grants rather than a dedicated
            # bucket, mirroring TIMESERIES_CACHE_BASE above.
            "METADATA_BUCKET": bucket_name,
            "METADATA_PREFIX": METADATA_PREFIX,
        }
        if data_repo:
            backend_env["DATA_REPO"] = data_repo
        # Signup request env vars (#5367): conditional so empty/unset values
        # are not injected, which lets the route handler's 503 guard fire
        # cleanly instead of surfacing as a downstream SES error.
        if signup_admin_email:
            backend_env["SIGNUP_ADMIN_EMAIL"] = signup_admin_email
        if signup_approval_base_url:
            backend_env["SIGNUP_APPROVAL_BASE_URL"] = signup_approval_base_url
        if signup_login_url:
            backend_env["SIGNUP_LOGIN_URL"] = signup_login_url

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

        # SES send permission for signup admin/user notification emails (#5367).
        # The Lambda calls ses:SendEmail to notify the admin of new account
        # requests (signup_request.py) and to tell approved users their login
        # is ready (signup_approved.py). The pension report Lambda also sends
        # email via SES and receives the same grant further below.
        backend_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail"],
                resources=["*"],
            )
        )

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

        ui_auth_domain_default = self.node.try_get_context("ui_auth_domain") or os.getenv(
            "UI_AUTH_DOMAIN"
        )
        ui_auth_domain_param = CfnParameter(
            self,
            "UiAuthDomain",
            type="String",
            allowed_pattern=".*",
            default=ui_auth_domain_default or "",
            description=(
                "Cognito hosted UI domain exported by StaticSiteStack, used by the frontend "
                "Cognito login flow (awsUiAuth.domain in /config response). "
                "Optional: leave empty to disable awsUiAuth in the backend /config response."
            ),
        )
        # Surfaced in the /config response as awsUiAuth so the frontend can
        # initiate the Cognito PKCE login flow (issue #4577). Added via
        # add_environment so the CfnParameter tokens resolve after definition.
        backend_fn.add_environment("UI_AUTH_DOMAIN", ui_auth_domain_param.value_as_string)
        backend_fn.add_environment("UI_AUTH_CLIENT_ID", ui_auth_client_id_param.value_as_string)

        # SmokeTestClient (static_site_stack.py) is a separate Cognito app client
        # used only by the deploy workflow's post-deploy smoke tests. Its tokens
        # must also pass backend_authorizer's audience check, otherwise every
        # Cognito-protected route (e.g. /groups) returns 401 for the smoke test
        # token even though /config and /health succeed (#4027). Optional with an
        # empty default so synths without a configured smoke-test client still work.
        smoke_test_client_id_default = self.node.try_get_context(
            "smoke_test_user_pool_client_id"
        ) or os.getenv("SMOKE_TEST_USER_POOL_CLIENT_ID")
        smoke_test_client_id_param = CfnParameter(
            self,
            "SmokeTestUserPoolClientId",
            type="String",
            allowed_pattern=".*",
            default=smoke_test_client_id_default or "",
            description=(
                "Cognito app client ID for the deploy workflow's SmokeTestClient, "
                "exported by StaticSiteStack. Optional: leave empty if smoke tests "
                "run unauthenticated."
            ),
        )
        # An empty SmokeTestUserPoolClientId (the default, and what the deploy
        # workflow passes if StaticSiteStack has no such output) must NOT become
        # an empty-string entry in the authorizer's JWT audience list below —
        # that would silently accept tokens with an empty `aud` claim. Gate the
        # smoke-test client with a condition so it's only added when non-empty.
        has_smoke_test_client = CfnCondition(
            self,
            "HasSmokeTestUserPoolClientId",
            expression=Fn.condition_not(
                Fn.condition_equals(smoke_test_client_id_param.value_as_string, "")
            ),
        )

        ui_auth_user_pool = cognito.UserPool.from_user_pool_id(
            self, "ImportedUiAuthUserPool", ui_auth_user_pool_id_param.value_as_string
        )
        # SmokeTestUserPoolClient is deliberately NOT added to user_pool_clients
        # here: HttpUserPoolAuthorizer synthesises every entry in that list into
        # JwtConfiguration.Audience unconditionally, which would put an
        # empty-string audience entry into the CloudFormation template before
        # the add_property_override below ever runs. The smoke-test client is
        # added to the audience solely via that conditional override (#4047
        # review).
        backend_authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            "BackendCognitoAuthorizer",
            ui_auth_user_pool,
            user_pool_clients=[
                cognito.UserPoolClient.from_user_pool_client_id(
                    self, "ImportedUiAuthUserPoolClient", ui_auth_client_id_param.value_as_string
                ),
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

        # Access logging on the default ($default) stage. The Cognito JWT
        # authorizer rejects unauthorized requests (e.g. the /owners 401 in
        # #4256) BEFORE they reach the Lambda, so those rejections are invisible
        # in the Lambda's own logs. Logging $context.authorizer.error alongside
        # the status/route makes gateway-level 401s observable in CloudWatch.
        # The format deliberately logs claims/status only — never the raw bearer
        # token — so no credentials land in the logs.
        access_log_group = logs.LogGroup(
            self,
            "BackendApiAccessLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        default_stage = backend_api.default_stage
        assert default_stage is not None, "BackendApi must expose a default stage"
        cfn_default_stage = default_stage.node.default_child
        assert isinstance(
            cfn_default_stage, apigwv2.CfnStage
        ), "Expected the default stage's default child to be a CfnStage"
        cfn_default_stage.add_property_override(
            "AccessLogSettings.DestinationArn", access_log_group.log_group_arn
        )
        cfn_default_stage.add_property_override("AccessLogSettings.Format", ACCESS_LOG_FORMAT)

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
        # POST /token/google exchanges a Google ID token (from the frontend's
        # standalone Google Identity Services sign-in, frontend/src/LoginPage.tsx)
        # for an app JWT. The caller authenticates with Google, not Cognito, and
        # frontend/src/LoginPage.tsx sends this request with no Authorization
        # header at all — backend_authorizer (Cognito JWT) would reject it with
        # 401 before backend.auth.verify_google_token ever runs, the same class
        # of bug fixed for GET /config in #3873.
        #
        # POST /token/cognito is NOT listed here: it stays behind the Cognito
        # authorizer via the /{proxy+} catch-all. The deployed frontend no longer
        # calls it — frontend/src/main.tsx applyCognitoIdToken now sends the
        # Cognito ID token directly as the Bearer header on every protected route,
        # which backend_authorizer validates (the ID token's `aud` matches the
        # configured JwtConfiguration.Audience) — see issue #4256. Leaving
        # /token/cognito authorizer-protected is correct: it requires the same
        # valid Cognito token, and the route's pool/client match by construction.
        # ui_auth_user_pool_id_param and
        # ui_auth_client_id_param (above) are documented as values exported by
        # StaticSiteStack's UiAuthUserPool/UiAuthClient (see
        # cdk/stacks/static_site_stack.py CfnOutputs UiAuthUserPoolId and
        # UiAuthUserPoolClientId). That same UiAuthClient.user_pool_client_id is
        # embedded in config.json's awsUiAuth.clientId (static_site_stack.py,
        # DeployRuntimeConfig), which is what the frontend uses to sign in via
        # Cognito and is also the ID token's `aud`. So backend_authorizer and the
        # frontend's Cognito sign-in resolve to the same UiAuthUserPool /
        # UiAuthClient — there is only one Cognito user pool in this stack
        # pairing, not two.
        backend_api.add_routes(
            path="/token/google",
            methods=[apigwv2.HttpMethod.POST],
            integration=backend_integration,
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )
        # POST /token is the Google-login exchange endpoint documented in
        # docs/AUTH.md ("The frontend POSTs { id_token } to POST /token") and
        # called directly by mobile/App.tsx. Like POST /token/google above, the
        # caller has no Cognito/app token yet — they are presenting a Google ID
        # token (or, in local/dev-only branches, a username) to obtain a backend
        # JWT. Without an explicit route here it falls through to the
        # /{proxy+} ANY catch-all and backend_authorizer rejects it with 401
        # before backend/app.py's login() ever runs — the same class of bug
        # already fixed for GET /config, POST /token/google, and POST
        # /signup/* (audit follow-up from #4798, issue #4800).
        backend_api.add_routes(
            path="/token",
            methods=[apigwv2.HttpMethod.POST],
            integration=backend_integration,
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )
        # POST /signup/request, and the /signup/approve and /signup/reject
        # GET+POST pairs, are the public account-request/admin-approval flow
        # (see the module docstring in backend/routes/signup.py). None of these
        # callers hold a Cognito token: the visitor requesting an account has no
        # session yet, and the admin authorises via an unguessable single-use
        # token embedded in the emailed link, not a Bearer header. Without an
        # explicit route here they fall through to the /{proxy+} ANY catch-all
        # below and get rejected with 401 before backend/routes/signup.py ever
        # runs — the same class of bug already fixed for GET /config in #3873
        # and POST /token/google above (#4785).
        for signup_path in ("/signup/request", "/signup/approve", "/signup/reject"):
            methods = (
                [apigwv2.HttpMethod.POST]
                if signup_path == "/signup/request"
                else [apigwv2.HttpMethod.GET, apigwv2.HttpMethod.POST]
            )
            backend_api.add_routes(
                path=signup_path,
                methods=methods,
                integration=backend_integration,
                authorizer=apigwv2.HttpNoneAuthorizer(),
            )
        # These explicit OPTIONS routes are NOT redundant with the HttpApi's
        # native `cors_preflight` config above (investigated for #4826).
        # AWS's own docs (Configure CORS for HTTP APIs -> "Configuring CORS
        # for an HTTP API with a $default route and an authorizer") say the
        # automatic preflight response only answers OPTIONS requests that
        # don't otherwise match a route. HTTP API route selection picks the
        # most specific match first: an exact "route + method" match beats a
        # "route + method with greedy {proxy+}" match, which beats $default
        # (see "Routing API requests" in the same guide). `ANY /` and
        # `ANY /{proxy+}` below are registered as explicit routes, and ANY
        # "matches all methods that you haven't defined for a route" - so
        # without an explicit OPTIONS route, an incoming OPTIONS request
        # would be caught by those ANY routes (not by the automatic CORS
        # response) and sent to backend_authorizer. Browsers send preflight
        # OPTIONS without an Authorization header, so the JWT authorizer
        # would reject it with 401 before CORS headers are ever returned -
        # reproducing #3945. Registering OPTIONS explicitly, with
        # HttpNoneAuthorizer(), is what gives it priority (exact method
        # match) over the ANY routes and keeps it off backend_authorizer.
        backend_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.OPTIONS],
            integration=backend_integration,
            authorizer=apigwv2.HttpNoneAuthorizer(),
        )
        backend_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.OPTIONS],
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

        # Override the synthesized audience so the smoke-test client ID is
        # included only when the parameter is actually set (#4027 review).
        # HttpUserPoolAuthorizer is not a Construct (no .node), so the
        # underlying CfnAuthorizer can only be located via backend_api's
        # construct tree. Assert exactly one CfnAuthorizer exists so that, if
        # a second authorizer is ever added to backend_api, synthesis fails
        # loudly instead of silently overriding the wrong resource.
        backend_cfn_authorizers = [
            child
            for child in backend_api.node.find_all()
            if isinstance(child, apigwv2.CfnAuthorizer)
        ]
        backend_cfn_authorizer = self._require_single_cfn_authorizer(backend_cfn_authorizers)
        backend_cfn_authorizer.add_property_override(
            "JwtConfiguration.Audience",
            Fn.condition_if(
                has_smoke_test_client.logical_id,
                [
                    ui_auth_client_id_param.value_as_string,
                    smoke_test_client_id_param.value_as_string,
                ],
                [ui_auth_client_id_param.value_as_string],
            ),
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

        # Scheduled function to fetch and record dividend transactions (issue #2750)
        dividend_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root),
            file="backend/Dockerfile.lambda",
            cmd=["backend.lambda_api.dividend_refresh.lambda_handler"],
        )
        dividend_env = {
            "APP_ENV": env,
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
            # refresh_dividends() reads/writes via AccountsStore, which reads
            # this env var at import time (backend/common/accounts_store.py).
            "WRITABLE_ACCOUNTS_PREFIX": WRITABLE_ACCOUNTS_PREFIX,
        }
        if data_repo:
            dividend_env["DATA_REPO"] = data_repo

        dividend_log_group = self._lambda_log_group(self, "DividendRefreshLambdaLogGroup")
        dividend_fn = _lambda.DockerImageFunction(
            self,
            "DividendRefreshLambda",
            code=dividend_code,
            environment=dividend_env,
            log_group=dividend_log_group,
            timeout=Duration.minutes(10),
            memory_size=512,
        )

        # DividendRefreshLambda: reads and writes writable-accounts/ only.
        # Audited: dividend_refresh.lambda_handler → refresh_dividends()
        # → S3AccountsStore.iter_transaction_documents()/read_document()/
        # edit_document()/rebuild_portfolio(), all scoped to
        # WRITABLE_ACCOUNTS_PREFIX (backend/common/dividends.py). It does not
        # call list_portfolios()/list_all_unique_tickers(), so unlike
        # PriceRefreshLambda it needs no ListBucket on accounts/. Instrument
        # currency lookups (get_instrument_meta) are get_object calls, not
        # list, so no separate instruments/ list grant is required either.
        self._grant_bucket_access(
            dividend_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=True,
            allow_list=True,
            list_prefix=lambda_list_prefixes["dividend_refresh"],
        )

        events.Rule(
            self,
            "DailyDividendRefresh",
            schedule=events.Schedule.cron(minute="0", hour="6"),
            targets=[targets.LambdaFunction(dividend_fn)],
        )

        # Scheduled function to email a pension performance report (issue #2758)
        pension_report_code = _lambda.DockerImageCode.from_image_asset(
            str(project_root),
            file="backend/Dockerfile.lambda",
            cmd=["backend.lambda_api.pension_report.lambda_handler"],
        )
        pension_report_env = {
            "APP_ENV": env,
            "DATA_BUCKET": bucket_name,
            "DATA_BRANCH": data_branch,
            "TIMESERIES_CACHE_BASE": f"s3://{bucket_name}/timeseries",
            # Pot-value snapshots persisted for YTD / period-over-period tracking
            # (backend/common/pension_snapshots.py), stored in the same data
            # bucket rather than a dedicated resource.
            "PENSION_SNAPSHOTS_URI": f"s3://{bucket_name}/pension-reports/pension_snapshots.json",
        }
        if data_repo:
            pension_report_env["DATA_REPO"] = data_repo

        pension_report_log_group = self._lambda_log_group(self, "PensionReportLambdaLogGroup")
        pension_report_fn = _lambda.DockerImageFunction(
            self,
            "PensionReportLambda",
            code=pension_report_code,
            environment=pension_report_env,
            log_group=pension_report_log_group,
            timeout=Duration.minutes(5),
            memory_size=512,
        )

        # PensionReportLambda: read-only on accounts/ (list_portfolios() ->
        # list_plots() needs ListBucket, same reasoning as price_refresh above),
        # plus write access scoped to pension-reports/ — the only prefix this
        # Lambda ever writes to (PENSION_SNAPSHOTS_URI above). Scoping the
        # s3:PutObject resource this way (rather than bucket-wide) prevents the
        # Lambda from writing outside its own snapshot path (issue #5013).
        self._grant_bucket_access(
            pension_report_fn,
            bucket=data_bucket,
            allow_read=True,
            allow_put=True,
            allow_list=True,
            list_prefix=lambda_list_prefixes["pension_report"],
            put_prefix="pension-reports",
        )

        # SES send permission for the pension report email (#5367).
        pension_report_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail"],
                resources=["*"],
            )
        )

        pension_report_schedule = (
            events.Schedule.cron(minute="0", hour="7", week_day="MON")
            if pension_report_cadence == "weekly"
            else events.Schedule.cron(minute="0", hour="7", day="1")
        )
        events.Rule(
            self,
            "PensionReportRun",
            schedule=pension_report_schedule,
            targets=[targets.LambdaFunction(pension_report_fn)],
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
        CfnOutput(
            self,
            "PensionReportLambdaLogGroupName",
            value=pension_report_log_group.log_group_name,
        )
        CfnOutput(self, "BackendLambdaErrorAlarmName", value=backend_error_alarm.alarm_name)
