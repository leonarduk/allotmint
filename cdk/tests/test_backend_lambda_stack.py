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
    _auth_env_vars = ("UI_AUTH_USER_POOL_ID", "UI_AUTH_USER_POOL_CLIENT_ID")
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
                # Audience must reference the Cognito app client ID parameter.
                "Audience": assertions.Match.array_with([
                    assertions.Match.object_like({"Ref": "UiAuthUserPoolClientId"})
                ]),
                # Issuer must be a CloudFormation expression (Fn::Join), not a
                # literal synth-time token like "${Token[...]}".
                "Issuer": assertions.Match.object_like(
                    {"Fn::Join": assertions.Match.any_value()}
                ),
            },
        },
    )


def test_backend_api_routes_require_cognito_authorizer(template):
    """All API Gateway routes must require Cognito JWT authorization except /health.

    /health is intentionally unauthenticated so that post-deploy probes and
    smoke tests can confirm Lambda is reachable without needing a Cognito token.
    Asserts the full route set so that adding any other unprotected route will
    fail this test rather than silently bypassing the authorizer.
    """
    UNAUTHENTICATED_ROUTES = {"GET /health"}

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
                {"Ref": assertions.Match.string_like_regexp("PriceRefreshLambda")}
            ),
        },
    )


def test_daily_price_refresh_rule_targets_alias_arn(template):
    """DailyPriceRefresh EventBridge rule must target the alias ARN, not the bare function ARN.

    Targeting the bare function ARN re-introduces the CDK authorization warning from
    issue #3073; only a qualified ARN (alias or version) avoids it.
    Match.array_with asserts at least one target matches — unrelated targets on the
    same rule (e.g. SNS) do not cause false failures.
    """
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
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
