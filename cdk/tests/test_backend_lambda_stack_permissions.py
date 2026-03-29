from __future__ import annotations

import sys
from pathlib import Path

from aws_cdk import App
from aws_cdk import aws_lambda as _lambda
from aws_cdk.assertions import Template

CDK_DIR = Path(__file__).resolve().parents[1]
if str(CDK_DIR) not in sys.path:
    sys.path.insert(0, str(CDK_DIR))

from stacks.backend_lambda_stack import BackendLambdaStack


BACKEND_LIST_PREFIXES = ("accounts", "queries", "timeseries/meta", "transactions")


def _stack_template() -> dict:
    app = App(
        context={
            "data_bucket": "unit-test-data-bucket",
            "app_env": "aws",
        }
    )
    stack = BackendLambdaStack(app, "BackendLambdaStackTest")
    return Template.from_stack(stack).to_json()


def _role_logical_id_for_lambda(template: dict, lambda_fragment: str) -> str:
    resources = template["Resources"]
    for logical_id, resource in resources.items():
        if resource.get("Type") != "AWS::Lambda::Function":
            continue
        if lambda_fragment not in logical_id:
            continue
        role = resource.get("Properties", {}).get("Role", {})
        get_att = role.get("Fn::GetAtt")
        if isinstance(get_att, list) and get_att:
            return get_att[0]
    raise AssertionError(f"Unable to find role for lambda fragment '{lambda_fragment}'")


def _s3_actions_for_role(template: dict, role_logical_id: str) -> set[str]:
    """Return only s3:* actions from inline policies attached to role_logical_id.

    Deliberately excludes AWS-managed policies (they have no Roles[] in template)
    and non-S3 actions, to avoid false positives from AWSLambdaBasicExecutionRole
    or future managed policies. Wildcards (s3:*) are detected and surfaced explicitly.
    """
    actions: set[str] = set()
    resources = template["Resources"]
    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        roles = resource.get("Properties", {}).get("Roles", [])
        role_refs = {
            role["Ref"]
            for role in roles
            if isinstance(role, dict) and isinstance(role.get("Ref"), str)
        }
        if role_logical_id not in role_refs:
            continue

        policy_doc = resource.get("Properties", {}).get("PolicyDocument", {})
        for statement in policy_doc.get("Statement", []):
            action = statement.get("Action", [])
            if isinstance(action, str):
                action = [action]
            for a in action:
                if a.startswith("s3:") or a == "*":
                    actions.add(a)

    return actions


def _resources_for_s3_action(template: dict, role_logical_id: str, target_action: str) -> list[str]:
    """Return all resource ARNs from statements that grant target_action to role_logical_id.

    CDK may produce the resource as a plain string or as a CloudFormation intrinsic
    (e.g. {"Fn::Join": [...]}). Plain strings are returned as-is; intrinsics are
    returned as their str() repr so callers can assert their structure if needed.
    """
    found: list[str] = []
    resources = template["Resources"]
    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        roles = resource.get("Properties", {}).get("Roles", [])
        role_refs = {
            r["Ref"]
            for r in roles
            if isinstance(r, dict) and isinstance(r.get("Ref"), str)
        }
        if role_logical_id not in role_refs:
            continue

        policy_doc = resource.get("Properties", {}).get("PolicyDocument", {})
        for statement in policy_doc.get("Statement", []):
            actions = statement.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if target_action not in actions:
                continue
            stmt_resources = statement.get("Resource", [])
            if isinstance(stmt_resources, str):
                stmt_resources = [stmt_resources]
            for r in stmt_resources:
                found.append(r if isinstance(r, str) else str(r))

    return found


def _conditions_for_s3_action(
    template: dict, role_logical_id: str, target_action: str
) -> list[dict]:
    """Return IAM Condition objects for statements granting target_action."""
    found: list[dict] = []
    resources = template["Resources"]
    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        roles = resource.get("Properties", {}).get("Roles", [])
        role_refs = {
            r["Ref"]
            for r in roles
            if isinstance(r, dict) and isinstance(r.get("Ref"), str)
        }
        if role_logical_id not in role_refs:
            continue

        policy_doc = resource.get("Properties", {}).get("PolicyDocument", {})
        for statement in policy_doc.get("Statement", []):
            actions = statement.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            if target_action not in actions:
                continue
            condition = statement.get("Condition")
            if isinstance(condition, dict):
                found.append(condition)

    return found


# Maximum allowed S3 action sets per Lambda role (upper bounds for least-privilege enforcement).
# Audit evidence:
#   BackendLambda      — full API; reads, writes, and lists portfolio/price data.
#   PriceRefreshLambda — calls _rolling_cache() → _save_parquet() which writes parquet to S3
#                        by known key (backend/timeseries/cache.py). No bucket enumeration.
#   TradingAgentLambda — calls load_prices_for_tickers() → load_meta_timeseries_range() which
#                        reads parquet from S3 by known key. No writes, no enumeration.
BACKEND_MAX_S3 = {"s3:GetObject", "s3:PutObject", "s3:ListBucket"}
REFRESH_MAX_S3 = {"s3:GetObject", "s3:PutObject"}
TRADING_MAX_S3 = {"s3:GetObject"}


def test_s3_permissions_are_scoped_per_lambda() -> None:
    """Assert minimum and maximum S3 action sets per Lambda role."""
    template = _stack_template()

    backend_role = _role_logical_id_for_lambda(template, "BackendLambda")
    refresh_role = _role_logical_id_for_lambda(template, "PriceRefreshLambda")
    trading_role = _role_logical_id_for_lambda(template, "TradingAgentLambda")

    backend_actions = _s3_actions_for_role(template, backend_role)
    refresh_actions = _s3_actions_for_role(template, refresh_role)
    trading_actions = _s3_actions_for_role(template, trading_role)

    # Minimum: required actions must be present
    assert {"s3:GetObject", "s3:PutObject", "s3:ListBucket"}.issubset(backend_actions), (
        f"BackendLambda missing required S3 actions: {backend_actions}"
    )
    assert {"s3:GetObject", "s3:PutObject"}.issubset(refresh_actions), (
        f"PriceRefreshLambda missing required S3 actions: {refresh_actions}"
    )
    assert {"s3:GetObject"}.issubset(trading_actions), (
        f"TradingAgentLambda missing required S3 actions: {trading_actions}"
    )

    # Maximum: no role may have S3 actions beyond its audited set (prevents privilege creep)
    assert backend_actions <= BACKEND_MAX_S3, (
        f"BackendLambda has unexpected S3 actions: {backend_actions - BACKEND_MAX_S3}"
    )
    assert refresh_actions <= REFRESH_MAX_S3, (
        f"PriceRefreshLambda has unexpected S3 actions: {refresh_actions - REFRESH_MAX_S3}"
    )
    assert trading_actions <= TRADING_MAX_S3, (
        f"TradingAgentLambda has unexpected S3 actions: {trading_actions - TRADING_MAX_S3}"
    )

    # Explicit absence checks (belt-and-suspenders on top of upper-bound)
    assert "s3:ListBucket" not in refresh_actions, (
        "PriceRefreshLambda should not have s3:ListBucket — all S3 access is by known key"
    )
    assert "s3:ListBucket" not in trading_actions, (
        "TradingAgentLambda should not have s3:ListBucket — all S3 access is by known key"
    )
    assert "s3:PutObject" not in trading_actions, (
        "TradingAgentLambda should not have s3:PutObject — read-only S3 access"
    )

    # s3:ListBucket must be scoped to the bucket ARN (no trailing /*), not the object ARN.
    # Granting ListBucket on /* is both functionally wrong (IAM ignores it) and overly broad.
    list_bucket_resources = _resources_for_s3_action(template, backend_role, "s3:ListBucket")
    assert list_bucket_resources, "BackendLambda has s3:ListBucket but no associated resource ARN"
    for arn in list_bucket_resources:
        assert not arn.endswith("/*"), (
            f"BackendLambda s3:ListBucket is scoped to an object ARN ({arn}); "
            "it must be scoped to the bucket ARN only (no trailing /*)"
        )

    list_bucket_conditions = _conditions_for_s3_action(template, backend_role, "s3:ListBucket")
    assert list_bucket_conditions, (
        "BackendLambda has s3:ListBucket but no associated IAM Condition"
    )
    expected_prefix_entries: list[str] = []
    for prefix in BACKEND_LIST_PREFIXES:
        expected_prefix_entries.extend([prefix, f"{prefix}/*"])
    expected_prefix = {"StringLike": {"s3:prefix": expected_prefix_entries}}
    assert expected_prefix in list_bucket_conditions, (
        "BackendLambda s3:ListBucket must be conditioned to all audited backend list prefixes"
    )


def test_non_listing_lambdas_do_not_have_listbucket_statement() -> None:
    template = _stack_template()

    refresh_role = _role_logical_id_for_lambda(template, "PriceRefreshLambda")
    trading_role = _role_logical_id_for_lambda(template, "TradingAgentLambda")

    assert not _conditions_for_s3_action(template, refresh_role, "s3:ListBucket"), (
        "PriceRefreshLambda should not have a ListBucket statement"
    )
    assert not _conditions_for_s3_action(template, trading_role, "s3:ListBucket"), (
        "TradingAgentLambda should not have a ListBucket statement"
    )


def test_grant_bucket_access_requires_list_prefix_when_allow_list_enabled() -> None:
    app = App()
    stack = BackendLambdaStack(app, "GrantBucketAccessValidationStack")
    fn = _lambda.Function(
        stack,
        "GrantBucketAccessValidationFn",
        runtime=_lambda.Runtime.PYTHON_3_11,
        code=_lambda.Code.from_inline("def handler(event, context):\n    return None\n"),
        handler="index.handler",
    )

    for invalid_prefix in (None, "", "   ", (), ("",)):
        try:
            BackendLambdaStack._grant_bucket_access(
                fn,
                bucket_name="unit-test-bucket",
                allow_read=False,
                allow_put=False,
                allow_list=True,
                list_prefix=invalid_prefix,
            )
        except ValueError:
            continue
        raise AssertionError(
            f"Expected ValueError for allow_list=True with list_prefix={invalid_prefix!r}"
        )


def test_grant_bucket_access_accepts_multiple_list_prefixes() -> None:
    app = App()
    stack = BackendLambdaStack(app, "GrantBucketAccessPrefixesStack")
    fn = _lambda.Function(
        stack,
        "GrantBucketAccessPrefixesFn",
        runtime=_lambda.Runtime.PYTHON_3_11,
        code=_lambda.Code.from_inline("def handler(event, context):\n    return None\n"),
        handler="index.handler",
    )

    BackendLambdaStack._grant_bucket_access(
        fn,
        bucket_name="unit-test-bucket",
        allow_read=False,
        allow_put=False,
        allow_list=True,
        list_prefix=BACKEND_LIST_PREFIXES,
    )

    template = Template.from_stack(stack).to_json()
    role_logical_id = _role_logical_id_for_lambda(template, "GrantBucketAccessPrefixesFn")
    conditions = _conditions_for_s3_action(template, role_logical_id, "s3:ListBucket")
    assert len(conditions) == 1, "Expected exactly one ListBucket statement"

    expected_prefix_entries: list[str] = []
    for prefix in BACKEND_LIST_PREFIXES:
        expected_prefix_entries.extend([prefix, f"{prefix}/*"])
    assert conditions[0] == {"StringLike": {"s3:prefix": expected_prefix_entries}}


def test_lambda_roles_do_not_have_s3_delete_permissions() -> None:
    template = _stack_template()

    role_fragments = ["BackendLambda", "PriceRefreshLambda", "TradingAgentLambda"]
    forbidden = {"s3:DeleteObject", "s3:DeleteObjectVersion"}

    for fragment in role_fragments:
        role = _role_logical_id_for_lambda(template, fragment)
        actions = _s3_actions_for_role(template, role)
        assert forbidden.isdisjoint(actions), (
            f"Found forbidden actions for {fragment}: {actions & forbidden}"
        )
        # Also catch wildcard grants which implicitly include delete
        assert "s3:*" not in actions and "*" not in actions, (
            f"Found wildcard grant for {fragment} which implicitly includes delete"
        )
