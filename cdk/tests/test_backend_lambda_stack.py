"""CDK assertion tests for BackendLambdaStack.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_backend_lambda_stack.py -v
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure the cdk package is importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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


def test_backend_lambda_timeout_is_at_least_30s(template):
    """BackendLambda must have a timeout > the 3 s default to survive cold starts."""
    functions = template.find_resources("AWS::Lambda::Function")
    backend_timeouts = [
        resource["Properties"].get("Timeout", 3)
        for resource in functions.values()
        if resource.get("Properties", {}).get("PackageType") == "Image"
        and "JWT_SECRET"
        in resource.get("Properties", {}).get("Environment", {}).get("Variables", {})
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


def test_backend_api_has_cognito_jwt_authorizer(template):
    """API Gateway must validate Cognito JWTs before invoking the backend Lambda."""
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "JWT",
            "IdentitySource": ["$request.header.Authorization"],
            "JwtConfiguration": {
                # Audience is conditionally built (Fn::If) so an empty
                # SmokeTestUserPoolClientId never adds an empty-string audience
                # entry — see test_backend_api_authorizer_audience_excludes_empty_smoke_test_client.
                "Audience": assertions.Match.object_like(
                    {"Fn::If": assertions.Match.any_value()}
                ),
                # Issuer must be a CloudFormation expression (Fn::Join), not a
                # literal synth-time token like "${Token[...]}".
                "Issuer": assertions.Match.object_like(
                    {"Fn::Join": assertions.Match.any_value()}
                ),
            },
        },
    )


def test_backend_api_authorizer_audience_excludes_empty_smoke_test_client(template):
    """When SmokeTestUserPoolClientId is empty (the default), the authorizer's
    JWT audience must fall back to only UiAuthUserPoolClientId. Otherwise an
    empty-string entry would be added to the audience list, which API Gateway
    would treat as a valid (if useless) audience value (#4027 review)."""
    json_template = template.to_json()

    conditions = json_template.get("Conditions", {})
    assert "HasSmokeTestUserPoolClientId" in conditions
    assert conditions["HasSmokeTestUserPoolClientId"] == {
        "Fn::Not": [{"Fn::Equals": [{"Ref": "SmokeTestUserPoolClientId"}, ""]}]
    }

    resources = template.find_resources("AWS::ApiGatewayV2::Authorizer")
    authorizer = next(iter(resources.values()))
    audience = authorizer["Properties"]["JwtConfiguration"]["Audience"]

    condition_name, with_smoke_client, without_smoke_client = audience["Fn::If"]
    assert condition_name == "HasSmokeTestUserPoolClientId"
    assert with_smoke_client == [
        {"Ref": "UiAuthUserPoolClientId"},
        {"Ref": "SmokeTestUserPoolClientId"},
    ]
    assert without_smoke_client == [{"Ref": "UiAuthUserPoolClientId"}]


def test_backend_api_authorizer_accepts_cognito_id_token_contract(template):
    """The authorizer audience is the UI app client ID, taken from the
    Authorization header. This is the contract the deployed frontend now relies
    on: frontend/src/main.tsx applyCognitoIdToken sends the Cognito ID token
    (whose `aud` claim equals the UI client ID) as `Authorization: Bearer`, so
    the gateway authorizer admits it before invoking the Lambda (#4256). If the
    audience ever stopped including UiAuthUserPoolClientId, the ID token would be
    rejected with 401 and this test would catch the regression."""
    resources = template.find_resources("AWS::ApiGatewayV2::Authorizer")
    authorizer = next(iter(resources.values()))
    properties = authorizer["Properties"]

    assert properties["IdentitySource"] == ["$request.header.Authorization"]

    audience = properties["JwtConfiguration"]["Audience"]
    _, with_smoke_client, without_smoke_client = audience["Fn::If"]
    # The UI client ID (the ID token's `aud`) must be present in both branches.
    assert {"Ref": "UiAuthUserPoolClientId"} in with_smoke_client
    assert {"Ref": "UiAuthUserPoolClientId"} in without_smoke_client


def test_backend_api_routes_require_cognito_authorizer(template):
    """All API Gateway routes must require Cognito JWT authorization except
    /health, GET /config, POST /token/google, the public /signup/* routes, and
    the CORS preflight OPTIONS routes.

    /health is intentionally unauthenticated so that post-deploy probes and
    smoke tests can confirm Lambda is reachable without needing a Cognito token.
    GET /config is intentionally unauthenticated because it is the frontend's
    pre-auth bootstrap endpoint (frontend/src/main.tsx Root.fetchConfig) used
    to determine whether auth is required at all; PUT /config remains
    JWT-protected via the /{proxy+} catch-all.
    POST /token/google is intentionally unauthenticated because it exchanges a
    Google ID token (frontend/src/LoginPage.tsx, sent with no Authorization
    header) for an app JWT — backend_authorizer would reject it with 401 before
    backend.auth.verify_google_token ever runs (#4240). POST /token/cognito is
    NOT in this set: it stays behind backend_authorizer via the /{proxy+}
    catch-all. The deployed frontend no longer calls it — frontend/src/main.tsx
    applyCognitoIdToken sends the Cognito ID token directly as the Bearer header,
    which backend_authorizer validates against the same user pool (#4256).
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
    UNAUTHENTICATED_ROUTES = {
        "GET /health",
        "GET /config",
        "POST /token/google",
        "POST /signup/request",
        "GET /signup/approve",
        "POST /signup/approve",
        "GET /signup/reject",
        "POST /signup/reject",
        "OPTIONS /",
        "OPTIONS /{proxy+}",
    }

    routes = template.find_resources("AWS::ApiGatewayV2::Route")
    assert routes, "Expected at least one API Gateway route"

    actual_none_routes = set()
    for logical_id, resource in routes.items():
        properties = resource["Properties"]
        route_key = properties.get("RouteKey", logical_id)
        auth_type = properties.get("AuthorizationType")
        if auth_type == "NONE":
            actual_none_routes.add(route_key)
        elif auth_type == "JWT":
            assert "AuthorizerId" in properties, (
                f"Route {route_key} must reference the JWT authorizer"
            )
        else:
            raise AssertionError(
                f"Route {route_key} has unexpected AuthorizationType {auth_type!r}; "
                "every route must be JWT-protected or listed in UNAUTHENTICATED_ROUTES"
            )

    assert actual_none_routes == UNAUTHENTICATED_ROUTES, (
        f"Unexpected unauthenticated routes: {actual_none_routes - UNAUTHENTICATED_ROUTES}; "
        f"Missing expected unauthenticated routes: {UNAUTHENTICATED_ROUTES - actual_none_routes}"
    )
    assert "GET /health" in actual_none_routes, (
        "GET /health route key not found in synthesized template — "
        "CDK may have changed the RouteKey format; update UNAUTHENTICATED_ROUTES to match"
    )
    # Explicit regression guard (#4248): POST /token/cognito is the deprecated
    # backend HS256 exchange (#4256) and must stay behind the Cognito JWT
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

    test_backend_api_routes_require_cognito_authorizer above already proves
    these routes are unauthenticated via a negative check (not in the JWT
    set). That alone would also pass if a future change accidentally moved
    them to a different non-JWT authorizer (e.g. IAM). This test documents
    and enforces the specific intended authorizer (#4799, follow-up from
    review of PR #4798).
    """
    routes = template.find_resources("AWS::ApiGatewayV2::Route")
    assert routes, "Expected at least one API Gateway route"

    signup_routes = {
        resource["Properties"].get("RouteKey", logical_id): resource["Properties"]
        for logical_id, resource in routes.items()
        if "/signup/" in resource["Properties"].get("RouteKey", "")
    }

    expected_route_keys = {
        "POST /signup/request",
        "GET /signup/approve",
        "POST /signup/approve",
        "GET /signup/reject",
        "POST /signup/reject",
    }
    assert set(signup_routes) == expected_route_keys, (
        f"Unexpected /signup/* route set: {set(signup_routes)}"
    )

    for route_key, properties in signup_routes.items():
        assert properties.get("AuthorizationType") == "NONE", (
            f"Route {route_key} must use HttpNoneAuthorizer (AuthorizationType "
            f"NONE), got {properties.get('AuthorizationType')!r}"
        )
        assert "AuthorizerId" not in properties, (
            f"Route {route_key} must not reference an authorizer resource"
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
# CfnAuthorizer count guard (issue #4057)
# ---------------------------------------------------------------------------


def test_require_single_cfn_authorizer_returns_sole_authorizer():
    sentinel = object()
    assert BackendLambdaStack._require_single_cfn_authorizer([sentinel]) is sentinel


@pytest.mark.parametrize("candidates", [[], [object(), object()]])
def test_require_single_cfn_authorizer_raises_value_error_when_not_exactly_one(candidates):
    """A missing or duplicated CfnAuthorizer must raise an explicit ValueError
    (not a bare assert, which is stripped under `python -O`) so a future change
    that adds a second authorizer to backend_api fails synthesis loudly."""
    with pytest.raises(ValueError, match="Expected exactly one CfnAuthorizer"):
        BackendLambdaStack._require_single_cfn_authorizer(candidates)


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
