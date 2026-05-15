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
    for logical_id, resource in routes.items():
        properties = resource["Properties"]
        route_key = properties.get("RouteKey", logical_id)
        if route_key in UNAUTHENTICATED_ROUTES:
            assert properties.get("AuthorizationType") == "NONE", (
                f"Route {route_key} is expected to be unauthenticated"
            )
        else:
            assert properties.get("AuthorizationType") == "JWT", (
                f"Route {route_key} must require Cognito JWT authorization"
            )
            assert "AuthorizerId" in properties, (
                f"Route {route_key} must reference the JWT authorizer"
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
