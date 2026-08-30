"""CDK assertion tests for BackendLambdaStack.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_backend_lambda_stack.py -v
"""
import json
import os

import pytest

# sys.path setup for `cdk.stacks...` imports lives in cdk/tests/conftest.py (#4929).
aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")

from aws_cdk import App, assertions  # noqa: E402

from cdk.stacks.backend_lambda_stack import BackendLambdaStack  # noqa: E402
from cdk.stacks.exports import BACKEND_API_URL_EXPORT  # noqa: E402  # stable name guard


@pytest.fixture(scope="module")
def template():
    """Synthesise BackendLambdaStack and return its CloudFormation template."""
    env_patch = {"JWT_SECRET": "test-secret", "GOOGLE_CLIENT_ID": "test-client-id"}
    for key, value in env_patch.items():
        os.environ.setdefault(key, value)
    # Remove optional auth env vars so CfnParameters have no Default,
    # keeping the synthesised template deterministic regardless of local env.
    # Also remove FRONTEND_ORIGIN/CORS_ORIGINS so the CORS allow_origins list
    # synthesises to its hardcoded default (see test_backend_api_cors_allow_origins_default).
    _auth_env_vars = (
        "UI_AUTH_USER_POOL_ID",
        "UI_AUTH_USER_POOL_CLIENT_ID",
        "UI_AUTH_DOMAIN",
        "FRONTEND_ORIGIN",
        "CORS_ORIGINS",
    )
    saved = {k: os.environ.pop(k, None) for k in _auth_env_vars}
    try:
        app = App()
        stack = BackendLambdaStack(app, "TestBackendStack")
        return assertions.Template.from_stack(stack)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Required secrets guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_var", ["JWT_SECRET", "GOOGLE_CLIENT_ID"])
def test_stack_raises_when_required_env_var_absent(missing_var, monkeypatch):
    monkeypatch.delenv(missing_var, raising=False)
    # Ensure the other required var is present so only one is missing at a time
    other = "GOOGLE_CLIENT_ID" if missing_var == "JWT_SECRET" else "JWT_SECRET"
    monkeypatch.setenv(other, "dummy")
    with pytest.raises(ValueError, match=missing_var):
        BackendLambdaStack(App(), "GuardTestStack")


# ---------------------------------------------------------------------------
# Data bucket properties
# ---------------------------------------------------------------------------

def test_data_bucket_versioning_enabled(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )


def test_data_bucket_sse_s3_encryption(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            }
        },
    )


def test_data_bucket_blocks_public_access(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_data_bucket_lifecycle_rule(template):
    """Noncurrent-version expiry lifecycle rule is present."""
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": [
                    assertions.Match.object_like(
                        {"NoncurrentVersionExpiration": {"NoncurrentDays": 30}}
                    )
                ]
            }
        },
    )


# ---------------------------------------------------------------------------
# IAM: least-privilege Lambda S3 access and broken DENY absence
# ---------------------------------------------------------------------------

def test_no_broken_deny_resource_policy_on_data_bucket(template):
    """The StringNotLike list-based DENY policy must not appear in the template.

    NOTE: enforce_ssl=True on the Bucket construct legitimately generates a
    DENY statement to block non-SSL requests — that is expected and correct.
    This test only asserts that the hand-rolled DenyNonLambdaPrincipalDataAccess
    statement (which used incorrect StringNotLike list semantics) is absent.
    """
    bucket_policies = template.find_resources("AWS::S3::BucketPolicy")
    for logical_id, resource in bucket_policies.items():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            assert stmt.get("Sid") != "DenyNonLambdaPrincipalDataAccess", (
                f"Broken DENY policy 'DenyNonLambdaPrincipalDataAccess' found in "
                f"bucket policy {logical_id} — this statement uses incorrect "
                f"StringNotLike list semantics that lock out Lambda roles: "
                f"{json.dumps(stmt)}"
            )


def test_lambda_roles_granted_expected_s3_actions_without_wildcards(template):
    """Stack grants expected S3 actions and avoids wildcard or destructive S3 permissions.

    s3:DeleteObject is explicitly checked for absence: the PR #2574 regression
    was caused by grant_read_write emitting DeleteObject as a side-effect of
    the broader grant. This test prevents that from recurring.
    """
    policies = template.find_resources("AWS::IAM::Policy")
    all_actions: list[str] = []
    for resource in policies.values():
        statements = (
            resource.get("Properties", {})
            .get("PolicyDocument", {})
            .get("Statement", [])
        )
        for stmt in statements:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            all_actions.extend(actions)

    assert any(a == "s3:GetObject" for a in all_actions), (
        "Expected s3:GetObject grant for Lambda roles"
    )
    assert any(a == "s3:PutObject" for a in all_actions), (
        "Expected s3:PutObject grant for Lambda roles"
    )
    assert any(a == "s3:ListBucket" for a in all_actions), (
        "Expected s3:ListBucket grant for Lambda roles that list known prefixes"
    )
    assert not any(a == "s3:*" for a in all_actions), (
        "Did not expect wildcard S3 permissions in Lambda IAM policies"
    )
    assert not any(a == "s3:DeleteObject" for a in all_actions), (
        "Did not expect s3:DeleteObject in Lambda IAM policies — "
        "grant_read_write emits this as a side-effect; use explicit action grants instead"
    )


def test_all_lambda_functions_have_data_bucket_env_var(template):
    """Every Lambda function must receive DATA_BUCKET pointing at the CDK-managed bucket.

    This guards against the build-arg bucket (seed_data_bucket) leaking into
    the runtime environment instead of the CDK-provisioned data_bucket.
    The CDK token for the bucket name resolves to a { Ref: ... } in the
    synthesised template, so we assert the key is present and its value is
    not a plain string (i.e., it is a token/Ref, not a baked-in bucket name).
    """
    lambda_functions = template.find_resources("AWS::Lambda::Function")
    for logical_id, resource in lambda_functions.items():
        properties = resource.get("Properties", {})
        if properties.get("PackageType") != "Image":
            # Skip CDK-generated helper Lambdas (e.g. log retention provider).
            continue
        env_vars = (
            properties
            .get("Environment", {})
            .get("Variables", {})
        )
        assert "DATA_BUCKET" in env_vars, (
            f"Lambda function {logical_id} is missing DATA_BUCKET environment variable"
        )
        # The value must be a CDK token (a dict with 'Ref' or 'Fn::...' key),
        # not a hardcoded string — ensuring it resolves to the managed bucket.
        bucket_val = env_vars["DATA_BUCKET"]
        assert not isinstance(bucket_val, str) or bucket_val == "", (
            f"Lambda {logical_id} DATA_BUCKET is a hardcoded string '{bucket_val}'; "
            "expected a CloudFormation token (Ref) to the CDK-managed bucket"
        )


# ---------------------------------------------------------------------------
# Observability, secrets, and cost guardrails
# ---------------------------------------------------------------------------

def test_all_lambda_functions_have_one_week_log_groups(template):
    resources = template.find_resources("AWS::Logs::LogGroup")
    lambda_log_groups = {
        logical_id: resource
        for logical_id, resource in resources.items()
        if logical_id.startswith(
            ("BackendLambdaLogGroup", "PriceRefreshLambdaLogGroup", "TradingAgentLambdaLogGroup")
        )
    }

    assert len(lambda_log_groups) == 3
    for logical_id, resource in lambda_log_groups.items():
        assert resource["Properties"]["RetentionInDays"] == 7, (
            f"Lambda log group {logical_id} must retain logs for one week"
        )
        assert resource["DeletionPolicy"] == "Delete", (
            f"Lambda log group {logical_id} must be destroyed with the stack"
        )

    lambda_functions = template.find_resources("AWS::Lambda::Function")
    image_functions = {
        logical_id: resource
        for logical_id, resource in lambda_functions.items()
        if resource.get("Properties", {}).get("PackageType") == "Image"
    }
    for logical_id, resource in image_functions.items():
        assert "LogGroup" in resource["Properties"].get("LoggingConfig", {}), (
            f"Lambda function {logical_id} must use an explicit log group"
        )
    assert template.find_resources("Custom::LogRetention") == {}


def test_all_lambda_functions_have_timeseries_cache_base_env_var(template):
    """Every image Lambda must have TIMESERIES_CACHE_BASE so timeseries/cache.py doesn't
    raise ValueError at import time (which causes 503 on every request)."""
    lambda_functions = template.find_resources("AWS::Lambda::Function")
    for logical_id, resource in lambda_functions.items():
        properties = resource.get("Properties", {})
        if properties.get("PackageType") != "Image":
            continue
        env_vars = properties.get("Environment", {}).get("Variables", {})
        assert "TIMESERIES_CACHE_BASE" in env_vars, (
            f"Lambda function {logical_id} is missing TIMESERIES_CACHE_BASE environment variable"
        )
        cache_base = env_vars["TIMESERIES_CACHE_BASE"]
        assert cache_base, (
            f"Lambda {logical_id} TIMESERIES_CACHE_BASE must not be empty"
        )


def test_backend_lambda_has_jwt_and_google_env_vars(template):
    # Only BackendLambda receives JWT_SECRET and GOOGLE_CLIENT_ID; the refresh
    # and agent Lambdas do not import backend.auth so they don't need them.
    # This assertion therefore targets BackendLambda specifically in practice.
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": assertions.Match.object_like(
                    {
                        "JWT_SECRET": assertions.Match.any_value(),
                        "GOOGLE_CLIENT_ID": assertions.Match.any_value(),
                    }
                )
            }
        },
    )


def test_backend_lambda_has_metadata_bucket_env_vars(template):
    """BackendLambda must have METADATA_BUCKET/METADATA_PREFIX so
    backend.common.instruments._s3_location() can resolve a writable S3
    location for auto-created instrument metadata instead of falling back to
    the read-only /var/task filesystem on Lambda (issue #4930)."""
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": assertions.Match.object_like(
                    {
                        "METADATA_BUCKET": assertions.Match.any_value(),
                        "METADATA_PREFIX": "instruments",
                    }
                )
            }
        },
    )


def test_backend_lambda_has_log_group_name_env_var(template):
    """BackendLambda must have BACKEND_LOG_GROUP_NAME so
    backend/routes/logs.py::_read_cloudwatch_logs() knows which CloudWatch log
    group to query for GET /logs on AWS, where there is no writable
    logs/backend.log to fall back to (issue #6140)."""
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": assertions.Match.object_like(
                    {"BACKEND_LOG_GROUP_NAME": assertions.Match.any_value()}
                )
            }
        },
    )


def test_backend_lambda_timeout_is_at_least_30s(template):
    """BackendLambda must have a timeout > the 3 s default to survive cold starts.

    Identified by JWT_SECRET *and* GOOGLE_CLIENT_ID together (matching
    test_backend_lambda_has_jwt_and_google_env_vars's own criteria): JWT_SECRET
    alone is no longer unique to BackendLambda since GatewayAuthorizerLambda
    (#7522) also needs it to verify demo-scoped tokens, but only BackendLambda
    also carries GOOGLE_CLIENT_ID.
    """
    functions = template.find_resources("AWS::Lambda::Function")
    backend_timeouts = [
        resource["Properties"].get("Timeout", 3)
        for resource in functions.values()
        if resource.get("Properties", {}).get("PackageType") == "Image"
        and {"JWT_SECRET", "GOOGLE_CLIENT_ID"}
        <= resource.get("Properties", {}).get("Environment", {}).get("Variables", {}).keys()
    ]
    assert backend_timeouts, "BackendLambda not found in synthesised template"
    assert all(t >= 30 for t in backend_timeouts), (
        f"BackendLambda timeout must be >= 30 s; found {backend_timeouts}"
    )


def test_price_refresh_trigger_on_deploy_exists(template):
    """A CDK Trigger must invoke PriceRefreshLambda synchronously on deploy.

    This ensures latest_prices.json is seeded in S3 on the first deployment
    without waiting for the daily EventBridge schedule.
    REQUEST_RESPONSE invocation blocks the CDK deploy until the Lambda finishes,
    guaranteeing the snapshot is present before the smoke-test job starts.
    The Trigger construct creates a Custom::Trigger CloudFormation resource whose
    HandlerArn must reference PriceRefreshLambda (not some other function).
    """
    trigger_resources = template.find_resources("Custom::Trigger")
    assert trigger_resources, (
        "Expected a Custom::Trigger resource from the CDK triggers.Trigger construct "
        "to invoke PriceRefreshLambda after first deploy"
    )

    # The trigger's HandlerArn must reference the PriceRefreshLambda function,
    # not an unrelated handler. CDK resolves HandlerArn as a Ref to a versioned
    # Lambda logical ID that starts with "PriceRefreshLambda".
    trigger_handler_arns = [
        resource.get("Properties", {}).get("HandlerArn")
        for resource in trigger_resources.values()
        if resource.get("Properties", {}).get("HandlerArn")
    ]
    assert trigger_handler_arns, (
        "Custom::Trigger must have a HandlerArn property referencing PriceRefreshLambda"
    )
    for arn in trigger_handler_arns:
        assert "PriceRefreshLambda" in json.dumps(arn), (
            f"Trigger HandlerArn {arn} does not reference PriceRefreshLambda; "
            "the trigger may be wired to the wrong function"
        )

    # The trigger must use REQUEST_RESPONSE (synchronous) so the CDK deploy blocks
    # until the price snapshot is written to S3. EVENT (async) allows the deploy to
    # complete before the Lambda finishes, leaving the smoke-test job with no snapshot.
    for resource in trigger_resources.values():
        invocation_type = resource.get("Properties", {}).get("InvocationType")
        assert invocation_type == "RequestResponse", (
            f"Custom::Trigger InvocationType must be 'RequestResponse' to block the deploy "
            f"until the price snapshot is seeded; found '{invocation_type}'. "
            "Change invocation_type=triggers.InvocationType.REQUEST_RESPONSE in the CDK stack."
        )


def test_price_refresh_lambda_has_sufficient_timeout(template):
    """PriceRefreshLambda must have a timeout long enough to fetch all portfolio prices.

    The default Lambda timeout is 3 seconds, which is far too short to call market
    data APIs for every ticker. The synchronous deploy Trigger (REQUEST_RESPONSE) will
    itself time out if PriceRefreshLambda times out, leaving the snapshot un-seeded.
    """
    functions = template.find_resources("AWS::Lambda::Function")
    # Identify PriceRefreshLambda by its ImageConfig.Command — the CDK
    # DockerImageCode.from_image_asset(..., cmd=[...]) call sets this property.
    refresh_timeouts = [
        resource["Properties"].get("Timeout", 3)
        for resource in functions.values()
        if resource.get("Properties", {}).get("PackageType") == "Image"
        and "price_refresh" in json.dumps(
            resource.get("Properties", {}).get("ImageConfig", {}).get("Command", [])
        )
    ]
    assert refresh_timeouts, (
        "PriceRefreshLambda not found in synthesised template via ImageConfig.Command; "
        "verify that DockerImageCode.from_image_asset uses cmd=['...price_refresh...']"
    )
    for t in refresh_timeouts:
        assert t >= 600, (
            f"PriceRefreshLambda timeout is {t}s — must be >= 600s (10 min) to complete "
            "a full price fetch for all portfolio tickers. "
            "Set timeout=Duration.minutes(10) in the CDK stack."
        )


def test_price_refresh_trigger_timeout_exceeds_lambda_timeout(template):
    """The CDK Trigger timeout must be strictly greater than PriceRefreshLambda's timeout.

    The Trigger custom resource provider invokes the Lambda with REQUEST_RESPONSE and
    waits for the response. If the provider's own timeout equals the Lambda's timeout,
    a race condition occurs: the Lambda may finish just as the provider times out,
    causing CloudFormation to receive a failure response even though the snapshot was
    written. The Trigger timeout must have meaningful headroom over the Lambda timeout.
    """
    functions = template.find_resources("AWS::Lambda::Function")
    refresh_timeout = next(
        (
            resource["Properties"].get("Timeout", 3)
            for resource in functions.values()
            if resource.get("Properties", {}).get("PackageType") == "Image"
            and "price_refresh" in json.dumps(
                resource.get("Properties", {}).get("ImageConfig", {}).get("Command", [])
            )
        ),
        None,
    )
    assert refresh_timeout is not None, "PriceRefreshLambda not found in synthesised template"

    trigger_resources = template.find_resources("Custom::Trigger")
    trigger_timeouts_ms = [
        int(resource.get("Properties", {}).get("Timeout", 0))
        for resource in trigger_resources.values()
        if resource.get("Properties", {}).get("HandlerArn")
        and "PriceRefreshLambda" in json.dumps(resource.get("Properties", {}).get("HandlerArn"))
    ]
    assert trigger_timeouts_ms, "No PriceRefreshOnDeploy Custom::Trigger timeout found"

    # CDK serialises the Trigger timeout in milliseconds.
    trigger_timeout_ms_raw = trigger_timeouts_ms[0]
    # Assert raw value is clearly milliseconds (> 60 000) so that if CDK ever
    # changes serialization units the error is obvious rather than the / 1000
    # conversion silently producing a plausible-looking but wrong seconds value.
    assert trigger_timeout_ms_raw > 60_000, (
        f"Trigger Timeout raw value {trigger_timeout_ms_raw} looks like seconds, not milliseconds; "
        "verify CDK is still serializing Duration.minutes() as milliseconds in Custom::Trigger"
    )
    trigger_timeout_s = trigger_timeout_ms_raw / 1000
    # Sanity-range check so a future CDK serialization-unit change is caught
    # immediately rather than producing a silent wrong comparison.
    assert 60 < trigger_timeout_s < 3600, (
        f"Trigger timeout {trigger_timeout_s}s (raw: {trigger_timeout_ms_raw}) looks wrong; "
        "verify CDK is still serializing Duration.minutes() as milliseconds in Custom::Trigger"
    )
    assert trigger_timeout_s > refresh_timeout, (
        f"Trigger timeout ({trigger_timeout_s}s) must be strictly greater than "
        f"PriceRefreshLambda timeout ({refresh_timeout}s) to avoid a race where the "
        "provider times out just as the Lambda finishes. "
        "Increase timeout=Duration.minutes(N) on the triggers.Trigger construct."
    )


def test_price_refresh_lambda_can_list_accounts_prefix(template):
    """PriceRefreshLambda's IAM policy must include s3:ListBucket on the accounts/ prefix.

    refresh_prices() → list_all_unique_tickers() → list_portfolios() → S3DataProvider.list_plots()
    calls list_objects_v2 on the accounts/ S3 prefix.  Without this, AWS returns
    AccessDenied (not 404), list_plots() raises ProviderUnavailable, and no tickers
    are discovered — so the price snapshot is never written.
    """
    policies = template.find_resources("AWS::IAM::Policy")

    # Identify IAM policies attached to PriceRefreshLambda's execution role
    # by looking for policies whose Roles reference the PriceRefreshLambda role.
    refresh_list_prefixes: list[str] = []
    for resource in policies.values():
        roles = json.dumps(resource.get("Properties", {}).get("Roles", []))
        if "PriceRefreshLambda" not in roles:
            continue
        stmts = resource.get("Properties", {}).get("PolicyDocument", {}).get("Statement", [])
        for stmt in stmts:
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if "s3:ListBucket" not in actions:
                continue
            prefixes = (
                stmt.get("Condition", {})
                .get("StringLike", {})
                .get("s3:prefix", [])
            )
            refresh_list_prefixes.extend(prefixes)

    assert refresh_list_prefixes, (
        "No s3:ListBucket statement found in PriceRefreshLambda's IAM policy. "
        "Add 'accounts' to lambda_list_prefixes['price_refresh'] in the CDK stack."
    )
    assert any("accounts" in p for p in refresh_list_prefixes), (
        f"PriceRefreshLambda's s3:ListBucket conditions do not include 'accounts' prefix; "
        f"found: {refresh_list_prefixes}. "
        "S3DataProvider.list_plots() calls list_objects_v2 on accounts/ and needs "
        "s3:ListBucket on that prefix to distinguish AccessDenied from NoSuchKey."
    )


def test_backend_error_alarm_exists(template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "Threshold": 1,
            "EvaluationPeriods": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        },
    )


def test_portfolio_group_5xx_alarm_uses_path_specific_log_metric(template):
    template.has_resource_properties(
        "AWS::Logs::MetricFilter",
        {
            "FilterPattern": (
                '{ ($.path = "/portfolio-group*") && ($.status = 5*) }'
            ),
            "MetricTransformations": [
                {
                    "DefaultValue": 0,
                    "MetricName": "PortfolioGroup5xx",
                    "MetricNamespace": "AllotMint/BackendApi",
                    "MetricValue": "1",
                }
            ],
        },
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "ComparisonOperator": "GreaterThanThreshold",
            "DatapointsToAlarm": 2,
            "EvaluationPeriods": 2,
            "MetricName": "PortfolioGroup5xx",
            "Namespace": "AllotMint/BackendApi",
            "Period": 60,
            "Statistic": "Sum",
            "Threshold": 0,
            "TreatMissingData": "notBreaching",
        },
    )


def test_portfolio_group_5xx_alarm_notifies_operational_topic(template):
    topics = template.find_resources("AWS::SNS::Topic")
    assert len(topics) == 1
    topic_logical_id = next(iter(topics))

    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    route_alarms = [
        alarm
        for alarm in alarms.values()
        if alarm.get("Properties", {}).get("MetricName") == "PortfolioGroup5xx"
    ]
    assert len(route_alarms) == 1
    assert route_alarms[0]["Properties"]["AlarmActions"] == [
        {"Ref": topic_logical_id}
    ]


def test_monthly_budget_exists(template):
    resources = template.find_resources("AWS::Budgets::Budget")
    assert resources, "Expected an AWS::Budgets::Budget resource"
    budget_props = next(iter(resources.values())).get("Properties", {}).get("Budget", {})
    assert budget_props.get("BudgetType") == "COST"
    assert budget_props.get("TimeUnit") == "MONTHLY"
    budget_limit = budget_props.get("BudgetLimit", {})
    assert float(budget_limit.get("Amount")) == 5.0
    assert budget_limit.get("Unit") == "USD"


def test_backend_api_auth_parameters_exist(template):
    template.has_parameter(
        "UiAuthUserPoolId",
        {
            "Type": "String",
            "AllowedPattern": ".+",
        },
    )
    template.has_parameter(
        "UiAuthUserPoolClientId",
        {
            "Type": "String",
            "AllowedPattern": ".+",
        },
    )
    params = template.to_json()["Parameters"]
    assert "Default" not in params["UiAuthUserPoolId"]
    assert "Default" not in params["UiAuthUserPoolClientId"]


def test_smoke_test_user_pool_client_id_parameter_is_optional(template):
    """SmokeTestUserPoolClientId must be optional so synths without a configured
    smoke-test client (e.g. local/non-prod) still work."""
    template.has_parameter(
        "SmokeTestUserPoolClientId",
        {
            "Type": "String",
            "AllowedPattern": ".*",
            "Default": "",
        },
    )


def test_backend_lambda_disables_app_jwt_decode_for_cognito_authorizer(template):
    """Lambda trusts API Gateway for Cognito auth and does not decode ID tokens as app JWTs."""
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": assertions.Match.object_like({"DISABLE_AUTH": "true"})
            }
        },
    )


def test_backend_api_has_gateway_lambda_authorizer(template):
    """API Gateway must run the demo/Cognito Lambda authorizer (#7522) before
    invoking the backend Lambda on the ANY / and ANY /{proxy+} routes.

    This replaces the old native Cognito HttpUserPoolAuthorizer (AuthorizerType
    JWT) with a REQUEST-type Lambda authorizer using payload format 2.0
    "simple" responses (EnableSimpleResponses), so it can accept either a
    valid Cognito ID token or a valid demo-scoped token
    (backend/lambda_api/demo_authorizer.py).
    """
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "REQUEST",
            "AuthorizerPayloadFormatVersion": "2.0",
            "EnableSimpleResponses": True,
            "IdentitySource": ["$request.header.Authorization"],
        },
    )


def test_gateway_authorizer_caching_is_disabled(template):
    """The gateway authorizer must not cache its decision (#7522).

    A cached "authorized" decision could keep admitting requests bearing a
    Cognito ID token past its real `exp` for up to the cache TTL, because
    BackendLambda itself trusts the gateway authorizer's decision for a
    Cognito token rather than independently re-checking its signature/expiry
    (see docs/AUTH.md). AuthorizerResultTtlInSeconds=0 keeps every request
    re-invoking this Lambda, matching the no-caching behaviour of the native
    Cognito JWT authorizer it replaced.
    """
    resources = template.find_resources("AWS::ApiGatewayV2::Authorizer")
    authorizer = next(iter(resources.values()))
    assert authorizer["Properties"]["AuthorizerResultTtlInSeconds"] == 0


def test_gateway_authorizer_invokes_dedicated_lambda(template):
    """The authorizer's AuthorizerUri must reference a Lambda function whose
    logical ID starts with GatewayAuthorizerLambda, not BackendLambda itself
    (this authorizer must be able to reject a request before BackendLambda
    ever runs, #7522)."""
    resources = template.find_resources("AWS::ApiGatewayV2::Authorizer")
    authorizer = next(iter(resources.values()))
    authorizer_uri = authorizer["Properties"]["AuthorizerUri"]

    join_parts = authorizer_uri["Fn::Join"][1]
    get_att_entries = [
        part["Fn::GetAtt"][0]
        for part in join_parts
        if isinstance(part, dict) and "Fn::GetAtt" in part
    ]
    assert any(logical_id.startswith("GatewayAuthorizerLambda") for logical_id in get_att_entries), (
        f"Expected AuthorizerUri to reference a GatewayAuthorizerLambda* function ARN, "
        f"found: {get_att_entries}"
    )


def test_gateway_authorizer_lambda_has_cognito_audience_and_jwt_secret_env_vars(template):
    """GatewayAuthorizerLambda must receive the same JWT_SECRET BackendLambda
    uses (so backend.auth.decode_demo_token can verify a demo token's HS256
    signature) and both configured Cognito app client IDs to check a Cognito
    ID token's audience against (#7522)."""
    resources = template.find_resources("AWS::Lambda::Function")
    matches = {
        logical_id: resource
        for logical_id, resource in resources.items()
        if logical_id.startswith("GatewayAuthorizerLambda")
    }
    assert matches, "Expected a GatewayAuthorizerLambda function in the synthesised template"

    for logical_id, resource in matches.items():
        env_vars = resource["Properties"].get("Environment", {}).get("Variables", {})
        assert "JWT_SECRET" in env_vars, f"{logical_id} is missing JWT_SECRET"
        assert env_vars.get("UI_AUTH_USER_POOL_CLIENT_ID") == {
            "Ref": "UiAuthUserPoolClientId"
        }, f"{logical_id} UI_AUTH_USER_POOL_CLIENT_ID must reference UiAuthUserPoolClientId"
        assert env_vars.get("SMOKE_TEST_USER_POOL_CLIENT_ID") == {
            "Ref": "SmokeTestUserPoolClientId"
        }, f"{logical_id} SMOKE_TEST_USER_POOL_CLIENT_ID must reference SmokeTestUserPoolClientId"


def _route_authorizer_map(template: dict) -> dict[str, dict]:
    """Return ``{route_key: properties}`` for every API Gateway route in ``template``.

    Shared by test_backend_api_routes_require_gateway_authorizer and
    test_signup_routes_use_http_none_authorizer, which both need the same
    RouteKey -> {AuthorizationType, AuthorizerId, ...} mapping (#4982). A pure
    function with no fixture dependencies, so it stays trivially reusable.
    """
    routes = template.find_resources("AWS::ApiGatewayV2::Route")
    return {
        resource["Properties"].get("RouteKey", logical_id): resource["Properties"]
        for logical_id, resource in routes.items()
    }


UNAUTHENTICATED_ROUTES = {
    "GET /health",
    "GET /config",
    "POST /token",
    "POST /token/google",
    "POST /signup/request",
    "GET /signup/approve",
    "POST /signup/approve",
    "GET /signup/reject",
    "POST /signup/reject",
    "OPTIONS /",
    "OPTIONS /{proxy+}",
}


def _assert_routes_use_http_none_authorizer(
    route_authorizer_map: dict, select, expected_route_keys: set
) -> None:
    """Positively assert that the routes matching ``select`` are registered
    with HttpNoneAuthorizer (AuthorizationType NONE, no AuthorizerId).

    Shared by the /signup/*, POST /token, and OPTIONS /{proxy+} tests below
    (#5329 follow-up) so each just states which routes it expects instead of
    repeating the set-equality + per-route AuthorizationType/AuthorizerId
    assertions. A route being unauthenticated only proves it is *absent*
    from the Cognito-JWT set (see test_backend_api_routes_require_gateway_authorizer
    below); this positively confirms the specific authorizer used instead.
    """
    matched = {
        route_key: properties
        for route_key, properties in route_authorizer_map.items()
        if select(route_key)
    }
    assert set(matched) == expected_route_keys, (
        f"Unexpected route set: {set(matched)}, expected {expected_route_keys}"
    )
    for route_key, properties in matched.items():
        assert properties.get("AuthorizationType") == "NONE", (
            f"Route {route_key} must use HttpNoneAuthorizer (AuthorizationType "
            f"NONE), got {properties.get('AuthorizationType')!r}"
        )
        assert "AuthorizerId" not in properties, (
            f"Route {route_key} must not reference an authorizer resource"
        )


def test_backend_api_routes_require_gateway_authorizer(template):
    """All API Gateway routes must require the demo/Cognito gateway authorizer
    (#7522) except /health, GET /config, POST /token, POST /token/google, the
    public /signup/* routes, and the CORS preflight OPTIONS routes.

    /health is intentionally unauthenticated so that post-deploy probes and
    smoke tests can confirm Lambda is reachable without needing a Cognito token.
    GET /config is intentionally unauthenticated because it is the frontend's
    pre-auth bootstrap endpoint (frontend/src/main.tsx Root.fetchConfig) used
    to determine whether auth is required at all; PUT /config remains
    protected via the /{proxy+} catch-all.
    POST /token is intentionally unauthenticated: it is the Google-login
    exchange endpoint documented in docs/AUTH.md and called directly by
    mobile/App.tsx. The caller presents a Google ID token (or, in local/dev
    branches, a username) with no Authorization header at all, so the gateway
    authorizer would reject it with 401 before backend/app.py's login() ever
    runs — the same class of bug as POST /token/google below (audit
    follow-up from #4798, issue #4800).
    POST /token/google is intentionally unauthenticated because it exchanges a
    Google ID token (frontend/src/LoginPage.tsx, sent with no Authorization
    header) for an app JWT — the gateway authorizer would reject it with 401
    before backend.auth.verify_google_token ever runs (#4240). POST
    /token/cognito is NOT in this set: it stays behind the gateway authorizer
    via the /{proxy+} catch-all. The deployed frontend no longer calls it —
    frontend/src/main.tsx applyCognitoIdToken sends the Cognito ID token
    directly as the Bearer header, which the gateway authorizer validates via
    backend.auth.is_cognito_id_token against the same client audience (#4256,
    #7522).
    POST /signup/request and the GET+POST /signup/approve and /signup/reject
    pairs are intentionally unauthenticated: the requesting visitor has no
    Cognito session yet, and the admin approval flow authorises via an
    unguessable single-use token in the emailed link rather than a Bearer
    header (see backend/routes/signup.py) — the same class of bug fixed here
    as for GET /config and POST /token/google (#4785).
    OPTIONS / and OPTIONS /{proxy+} are unauthenticated so that browser CORS
    preflight requests (which never carry an Authorization header) are not
    rejected with 401 before the real request is sent (see issue #3945).
    Asserts the full route set so that adding any other unprotected route will
    fail this test rather than silently bypassing the authorizer.
    """
    route_authorizer_map = _route_authorizer_map(template)
    assert route_authorizer_map, "Expected at least one API Gateway route"

    actual_none_routes = set()
    actual_custom_routes = set()
    for route_key, properties in route_authorizer_map.items():
        auth_type = properties.get("AuthorizationType")
        if auth_type == "NONE":
            actual_none_routes.add(route_key)
        elif auth_type == "CUSTOM":
            assert "AuthorizerId" in properties, (
                f"Route {route_key} must reference the gateway authorizer"
            )
            actual_custom_routes.add(route_key)
        else:
            raise AssertionError(
                f"Route {route_key} has unexpected AuthorizationType {auth_type!r}; "
                "every route must be gateway-authorizer-protected (CUSTOM) or "
                "listed in UNAUTHENTICATED_ROUTES"
            )

    assert actual_none_routes == UNAUTHENTICATED_ROUTES, (
        f"Unexpected unauthenticated routes: {actual_none_routes - UNAUTHENTICATED_ROUTES}; "
        f"Missing expected unauthenticated routes: {UNAUTHENTICATED_ROUTES - actual_none_routes}"
    )
    assert "GET /health" in actual_none_routes, (
        "GET /health route key not found in synthesized template — "
        "CDK may have changed the RouteKey format; update UNAUTHENTICATED_ROUTES to match"
    )
    # Only the ANY / and ANY /{proxy+} catch-alls are CUSTOM-authorizer routes
    # (#7522) — every other protected path reaches them via /{proxy+}.
    assert actual_custom_routes == {"ANY /", "ANY /{proxy+}"}, (
        f"Expected exactly ANY / and ANY /{{proxy+}} behind the gateway authorizer, "
        f"found: {actual_custom_routes}"
    )
    # Explicit regression guard (#4248): POST /token/cognito is the deprecated
    # backend HS256 exchange (#4256) and must stay behind the gateway
    # authorizer via the /{proxy+} catch-all, unlike POST /token/google above.
    # The set-equality assert above would already catch this if /token/cognito
    # had its own explicit NONE route, but it says nothing about a route that
    # doesn't exist as a distinct resource at all — this assertion documents
    # the intent directly rather than relying on that implication.
    assert "POST /token/cognito" not in UNAUTHENTICATED_ROUTES
    assert "POST /token/cognito" not in actual_none_routes


def test_signup_routes_use_http_none_authorizer(template):
    """Positively assert that the /signup/* routes are registered with
    HttpNoneAuthorizer (AuthorizationType NONE), rather than only checking
    that they are absent from the Cognito-authorizer set.

    test_backend_api_routes_require_gateway_authorizer above already proves
    these routes are unauthenticated via a negative check (not in the JWT
    set). That alone would also pass if a future change accidentally moved
    them to a different non-JWT authorizer (e.g. IAM). This test documents
    and enforces the specific intended authorizer (#4799, follow-up from
    review of PR #4798).
    """
    route_authorizer_map = _route_authorizer_map(template)
    assert route_authorizer_map, "Expected at least one API Gateway route"

    expected_route_keys = {
        "POST /signup/request",
        "GET /signup/approve",
        "POST /signup/approve",
        "GET /signup/reject",
        "POST /signup/reject",
    }
    _assert_routes_use_http_none_authorizer(
        route_authorizer_map, lambda k: "/signup/" in k, expected_route_keys
    )


def test_token_route_uses_http_none_authorizer(template):
    """Positively assert that POST /token is registered with
    HttpNoneAuthorizer (AuthorizationType NONE), not just absent from the
    Cognito-authorizer set.

    test_backend_api_routes_require_gateway_authorizer above already proves
    this route is unauthenticated via a negative check (not in the JWT set).
    This test documents and enforces the specific intended authorizer,
    mirroring test_signup_routes_use_http_none_authorizer (audit follow-up
    from #4798, issue #4800).
    """
    route_authorizer_map = _route_authorizer_map(template)
    assert route_authorizer_map, "Expected at least one API Gateway route"

    _assert_routes_use_http_none_authorizer(
        route_authorizer_map, lambda k: k == "POST /token", {"POST /token"}
    )


def test_options_proxy_route_uses_http_none_authorizer(template):
    """Positively assert that OPTIONS /{proxy+} — the CORS preflight route
    that covers every Cognito-JWT-protected endpoint behind the catch-all
    (e.g. GET /owners, GET /portfolio-group/{slug}) — is registered with
    HttpNoneAuthorizer (AuthorizationType NONE), not just absent from the
    Cognito-authorizer set.

    This is the regression guard for issue #3945: browser CORS preflight
    requests never carry an Authorization header, so if this route were
    ever put behind the JWT authorizer, every authenticated endpoint would
    start failing preflight with 401 before the real (GET/POST/etc.) request
    was even sent — a failure mode that only shows up as a broken frontend,
    not as an API Gateway error on the "real" route itself.

    test_backend_api_routes_require_gateway_authorizer above already proves
    OPTIONS /{proxy+} is unauthenticated via a negative check (it is part of
    the UNAUTHENTICATED_ROUTES set). This test documents and enforces the
    specific intended authorizer directly, mirroring
    test_signup_routes_use_http_none_authorizer and
    test_token_route_uses_http_none_authorizer above.
    """
    route_authorizer_map = _route_authorizer_map(template)
    assert route_authorizer_map, "Expected at least one API Gateway route"

    _assert_routes_use_http_none_authorizer(
        route_authorizer_map,
        lambda k: k == "OPTIONS /{proxy+}",
        {"OPTIONS /{proxy+}"},
    )


# ---------------------------------------------------------------------------
# CORS configuration (issue #4828)
# ---------------------------------------------------------------------------


def test_backend_api_cors_allow_origins_includes_frontend_origin(monkeypatch):
    """When FRONTEND_ORIGIN is set, it must be included in the HttpApi's CORS
    AllowOrigins, inserted first so it takes priority over the hardcoded base
    list (issue #3958)."""
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://preview.allotmint.io")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    app = App()
    stack = BackendLambdaStack(app, "FrontendOriginTestStack")
    template = assertions.Template.from_stack(stack)

    apis = template.find_resources("AWS::ApiGatewayV2::Api")
    api = next(iter(apis.values()))
    cors = api["Properties"]["CorsConfiguration"]
    assert cors["AllowOrigins"] == [
        "https://preview.allotmint.io",
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.allotmint.io",
    ]


def test_backend_api_cors_allow_origins_default(template):
    """With FRONTEND_ORIGIN/CORS_ORIGINS unset (the `template` fixture's default
    env), the HttpApi's CORS preflight AllowOrigins must be exactly the
    hardcoded base list, in order: the two local dev servers, then prod.

    This pins the default list so a future edit to backend_lambda_stack.py's
    cors_origins construction is caught here rather than only at deploy time.
    """
    apis = template.find_resources("AWS::ApiGatewayV2::Api")
    assert apis, "Expected an AWS::ApiGatewayV2::Api resource"

    api = next(iter(apis.values()))
    cors = api["Properties"]["CorsConfiguration"]
    assert cors["AllowOrigins"] == [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.allotmint.io",
    ]
    assert cors["AllowCredentials"] is True
    assert cors["AllowMethods"] == ["*"]
    assert set(cors["AllowHeaders"]) == {"Authorization", "Content-Type", "X-CSRFToken"}


# ---------------------------------------------------------------------------
# API Gateway access logging (auth-boundary observability — issue #4255)
# ---------------------------------------------------------------------------


def test_backend_api_stage_has_access_logging(template):
    """The HTTP API default stage must have access logging configured so that
    authorizer rejections (Cognito JWT 401s that never reach the Lambda) are
    observable in CloudWatch.

    Asserts the stage points at a CloudWatch log group and that the log format
    includes the authorizer error, status, and route — but not the raw token.
    """
    stages = template.find_resources("AWS::ApiGatewayV2::Stage")
    assert stages, "Expected an AWS::ApiGatewayV2::Stage resource"

    access_log_settings = [
        resource["Properties"].get("AccessLogSettings")
        for resource in stages.values()
        if resource.get("Properties", {}).get("AccessLogSettings")
    ]
    assert access_log_settings, (
        "No AWS::ApiGatewayV2::Stage has AccessLogSettings configured; "
        "the default stage must write access logs to CloudWatch so gateway "
        "authorizer 401s are observable (issue #4255)"
    )

    settings = access_log_settings[0]
    assert settings.get("DestinationArn"), (
        "AccessLogSettings must reference a CloudWatch log group DestinationArn"
    )
    fmt = settings.get("Format", "")
    assert "$context.authorizer.error" in fmt, (
        "Access log format must include $context.authorizer.error so gateway "
        "authorizer rejections record a reason"
    )
    assert "$context.status" in fmt, "Access log format must include $context.status"
    assert "$context.routeKey" in fmt, "Access log format must include $context.routeKey"
    assert "$context.path" in fmt, (
        "Access log format must include $context.path: portfolio-group routes "
        "are only registered via the ANY /{proxy+} catch-all, so routeKey alone "
        "cannot distinguish them for the PortfolioGroup5xx metric filter"
    )
    assert "$context.identity.sourceIp" in fmt, (
        "Access log format must include $context.identity.sourceIp for debugging context"
    )

    # Guard against ever logging the raw bearer token / Authorization header.
    # Parses the format's context-variable values instead of substring-matching
    # the raw string, so it doesn't false-positive on unrelated fields (e.g.
    # $context.identity.sourceIp, which legitimately contains "identity").
    fmt_values = json.loads(fmt).values()
    assert not any("authorization" in value.lower() for value in fmt_values), (
        "Access log format must not capture the Authorization header / raw token"
    )
    assert not any("request.header" in value.lower() for value in fmt_values), (
        "Access log format must not reference raw request headers"
    )


def test_backend_api_access_log_group_has_one_week_retention(template):
    """The access-log group must use the stack's standard one-week retention
    and be destroyed with the stack, matching the Lambda log groups."""
    resources = template.find_resources("AWS::Logs::LogGroup")
    access_log_groups = {
        logical_id: resource
        for logical_id, resource in resources.items()
        if logical_id.startswith("BackendApiAccessLogGroup")
    }
    assert access_log_groups, "Expected a BackendApiAccessLogGroup log group"
    for logical_id, resource in access_log_groups.items():
        assert resource["Properties"]["RetentionInDays"] == 7, (
            f"{logical_id} must retain access logs for one week"
        )
        assert resource["DeletionPolicy"] == "Delete", (
            f"{logical_id} must be destroyed with the stack"
        )


# ---------------------------------------------------------------------------
# CfnOutputs
# ---------------------------------------------------------------------------

def test_backend_api_url_output_exists(template):
    template.has_output("BackendApiUrl", {})


def test_backend_api_url_output_has_stable_export_name(template):
    """BackendApiUrl must have a stable export name for workflow and cross-stack consumers.

    The deployment workflow reads this export via `aws cloudformation describe-stacks`
    and passes the value to StaticSiteStack at deploy time via --parameters.
    StaticSiteStack does NOT use Fn::ImportValue (CDK's BucketDeployment renderData
    validator rejects it); it receives the URL through a CfnParameter instead.

    Renaming this export requires updating the workflow query and any future consumers.
    """
    template.has_output(
        "BackendApiUrl",
        {"Export": {"Name": BACKEND_API_URL_EXPORT}},
    )


def test_data_bucket_name_output_exists(template):
    template.has_output("DataBucketName", {})


def test_lambda_log_group_name_outputs_exist(template):
    for output_name in (
        "BackendLambdaLogGroupName",
        "PriceRefreshLambdaLogGroupName",
        "TradingAgentLambdaLogGroupName",
    ):
        template.has_output(output_name, {})


def test_backend_lambda_error_alarm_output_exists(template):
    template.has_output("BackendLambdaErrorAlarmName", {})


def test_portfolio_group_5xx_alarm_output_exists(template):
    template.has_output("PortfolioGroup5xxAlarmName", {})


# ---------------------------------------------------------------------------
# PriceRefreshLambda alias and qualified EventBridge target
# ---------------------------------------------------------------------------


def test_price_refresh_lambda_live_alias_exists(template):
    """AWS::Lambda::Alias with Name='live' must point at a PriceRefreshLambda version.

    Without the alias, EventBridge and the deploy Trigger invoke the unqualified
    function ARN, which triggers a CDK authorization warning (issue #3073) because
    AWS Lambda started requiring qualified ARNs for AddPermission calls.
    """
    template.has_resource_properties(
        "AWS::Lambda::Alias",
        {
            "Name": "live",
            "FunctionName": assertions.Match.object_like(
                {"Ref": assertions.Match.string_like_regexp("PriceRefreshLambda")}
            ),
            "FunctionVersion": assertions.Match.object_like(
                {"Fn::GetAtt": assertions.Match.array_with([
                    assertions.Match.string_like_regexp("PriceRefreshLambda")
                ])}
            ),
        },
    )


def test_daily_price_refresh_rule_targets_alias_arn(template):
    """DailyPriceRefresh EventBridge rule must target the alias ARN, not the bare function ARN.

    Targeting the bare function ARN re-introduces the CDK authorization warning from
    issue #3073; only a qualified ARN (alias or version) avoids it.
    ScheduleExpression pins this assertion to the midnight price-refresh rule
    (not the 1 AM trading-agent rule or any future rule).
    Match.array_with on Targets means unrelated targets on the same rule (e.g. SNS)
    do not cause false failures.
    """
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": "cron(0 0 * * ? *)",
            "Targets": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Arn": assertions.Match.object_like(
                        {"Ref": assertions.Match.string_like_regexp("PriceRefreshLambdaLiveAlias")}
                    )
                })
            ]),
        },
    )


def test_daily_price_refresh_lambda_permission_scoped_to_alias(template):
    """The Lambda invocation permission for EventBridge must be scoped to the alias ARN.

    A permission on the unqualified function ARN cannot authorize invocations of a
    qualified ARN (alias/version), so the permission must reference the alias.
    """
    template.has_resource_properties(
        "AWS::Lambda::Permission",
        {
            "Action": "lambda:InvokeFunction",
            "Principal": "events.amazonaws.com",
            "FunctionName": assertions.Match.object_like(
                {"Ref": assertions.Match.string_like_regexp("PriceRefreshLambdaLiveAlias")}
            ),
        },
    )


# ---------------------------------------------------------------------------
# PensionReportLambda / PensionReportRun (issue #2758)
# ---------------------------------------------------------------------------


def test_pension_report_rule_defaults_to_weekly_monday_cron(template):
    """With no cadence context/env override, the rule fires weekly on Monday."""
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": assertions.Match.string_like_regexp(r"cron\(0 7 \? \* MON \*\)"),
            "Targets": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Arn": assertions.Match.object_like(
                        {"Fn::GetAtt": assertions.Match.array_with([
                            assertions.Match.string_like_regexp("PensionReportLambda")
                        ])}
                    )
                })
            ]),
        },
    )


def test_pension_report_rule_monthly_cadence_via_context():
    """pension_report_cadence="monthly" produces a 1st-of-month cron, not the weekly default."""
    env_patch = {"JWT_SECRET": "test-secret", "GOOGLE_CLIENT_ID": "test-client-id"}
    for key, value in env_patch.items():
        os.environ.setdefault(key, value)

    app = App(context={"pension_report_cadence": "monthly"})
    stack = BackendLambdaStack(app, "MonthlyPensionReportStack")
    monthly_template = assertions.Template.from_stack(stack)

    monthly_template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": assertions.Match.string_like_regexp(r"cron\(0 7 1 \* \? \*\)"),
        },
    )


def test_pension_report_rule_rejects_invalid_cadence():
    env_patch = {"JWT_SECRET": "test-secret", "GOOGLE_CLIENT_ID": "test-client-id"}
    for key, value in env_patch.items():
        os.environ.setdefault(key, value)

    with pytest.raises(ValueError, match="pension_report_cadence"):
        BackendLambdaStack(
            App(context={"pension_report_cadence": "daily"}), "InvalidCadenceStack"
        )


def test_pension_report_lambda_read_only_on_accounts_prefix(template):
    """PensionReportLambda gets scoped ListBucket on accounts/ (list_portfolios() needs it)."""
    policies = template.find_resources("AWS::IAM::Policy")
    matched = False
    for resource in policies.values():
        role_refs = [
            ref.get("Ref", "")
            for ref in resource.get("Properties", {}).get("Roles", [])
            if isinstance(ref, dict)
        ]
        if not any("PensionReportLambda" in ref for ref in role_refs):
            continue
        statements = resource["Properties"]["PolicyDocument"]["Statement"]
        for stmt in statements:
            if stmt.get("Action") == "s3:ListBucket":
                conditions = stmt.get("Condition", {}).get("StringLike", {}).get("s3:prefix", [])
                if "accounts" in conditions:
                    matched = True
    assert matched, "Expected a ListBucket statement scoped to the accounts/ prefix"


def test_pension_report_lambda_env_includes_snapshots_uri(template):
    """PENSION_SNAPSHOTS_URI is built from the data bucket ref via Fn::Join, not a plain string."""
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": assertions.Match.object_like(
                    {
                        "PENSION_SNAPSHOTS_URI": {
                            "Fn::Join": assertions.Match.array_with([
                                assertions.Match.array_with([
                                    assertions.Match.string_like_regexp(
                                        r"/pension-reports/pension_snapshots\.json$"
                                    )
                                ])
                            ])
                        }
                    }
                )
            }
        },
    )
