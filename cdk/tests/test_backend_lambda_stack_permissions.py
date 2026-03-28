from __future__ import annotations

from pathlib import Path
import sys

from aws_cdk import App
from aws_cdk.assertions import Template

CDK_DIR = Path(__file__).resolve().parents[1]
if str(CDK_DIR) not in sys.path:
    sys.path.insert(0, str(CDK_DIR))

from stacks.backend_lambda_stack import BackendLambdaStack


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


def _policy_actions_for_role(template: dict, role_logical_id: str) -> set[str]:
    actions: set[str] = set()
    resources = template["Resources"]
    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        policy_doc = resource.get("Properties", {}).get("PolicyDocument", {})
        statements = policy_doc.get("Statement", [])
        roles = resource.get("Properties", {}).get("Roles", [])
        role_refs = {
            role["Ref"]
            for role in roles
            if isinstance(role, dict) and isinstance(role.get("Ref"), str)
        }
        if role_logical_id not in role_refs:
            continue

        for statement in statements:
            action = statement.get("Action", [])
            if isinstance(action, str):
                actions.add(action)
            else:
                actions.update(action)

    return actions


def test_s3_permissions_are_scoped_per_lambda() -> None:
    template = _stack_template()

    backend_role = _role_logical_id_for_lambda(template, "BackendLambda")
    refresh_role = _role_logical_id_for_lambda(template, "PriceRefreshLambda")
    trading_role = _role_logical_id_for_lambda(template, "TradingAgentLambda")

    backend_actions = _policy_actions_for_role(template, backend_role)
    refresh_actions = _policy_actions_for_role(template, refresh_role)
    trading_actions = _policy_actions_for_role(template, trading_role)

    assert {"s3:GetObject", "s3:PutObject", "s3:ListBucket"}.issubset(backend_actions)
    assert "s3:PutObject" not in refresh_actions
    assert "s3:PutObject" not in trading_actions
    assert {"s3:GetObject", "s3:ListBucket"}.issubset(refresh_actions)
    assert {"s3:GetObject", "s3:ListBucket"}.issubset(trading_actions)



def test_lambda_roles_do_not_have_s3_delete_permissions() -> None:
    template = _stack_template()

    role_fragments = ["BackendLambda", "PriceRefreshLambda", "TradingAgentLambda"]
    forbidden = {"s3:DeleteObject", "s3:DeleteObjectVersion"}

    for fragment in role_fragments:
        role = _role_logical_id_for_lambda(template, fragment)
        actions = _policy_actions_for_role(template, role)
        assert forbidden.isdisjoint(actions), f"Found forbidden actions for {fragment}: {actions & forbidden}"
