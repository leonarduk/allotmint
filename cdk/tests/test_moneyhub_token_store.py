from __future__ import annotations

import ast
from pathlib import Path

import pytest
from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Match, Template
from stacks._paths import resolve_app_root
from stacks.moneyhub_token_store import (
    MONEYHUB_TOKEN_PARAMETER_PREFIX,
    MoneyhubTokenStore,
)

CDK_DIR = Path(__file__).resolve().parents[1]


def test_grant_is_scoped_to_moneyhub_token_descendants() -> None:
    app = App()
    stack = Stack(app, "TestStack")
    role = iam.Role(
        stack,
        "Role",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    )
    token_store = MoneyhubTokenStore(stack, "TokenStore")

    token_store.grant_read_write(role)

    Template.from_stack(stack).has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        {
                            "Action": ["ssm:GetParameter", "ssm:PutParameter"],
                            "Effect": "Allow",
                            "Resource": {
                                "Fn::Join": [
                                    "",
                                    [
                                        "arn:",
                                        {"Ref": "AWS::Partition"},
                                        ":ssm:",
                                        {"Ref": "AWS::Region"},
                                        ":",
                                        {"Ref": "AWS::AccountId"},
                                        ":parameter/allotmint/moneyhub/tokens/*",
                                    ],
                                ]
                            },
                        }
                    ]
                )
            }
        },
    )


def test_token_prefix_is_stable() -> None:
    assert MONEYHUB_TOKEN_PARAMETER_PREFIX == "/allotmint/moneyhub/tokens"


def _fallback_string_literal(source_path: Path, assigned_name: str) -> str:
    """Statically extract the fallback string literal assigned to ``assigned_name``.

    Mirrors the helper in test_backend_lambda_stack_permissions.py: parses
    with ``ast`` rather than importing the module, since the CDK test
    environment does not install backend runtime dependencies.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == assigned_name for t in node.targets):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                return sub.value
    raise AssertionError(f"Could not statically find a fallback literal for {assigned_name!r} in {source_path}")


def test_token_prefix_matches_backend_moneyhub_tokens_uri_template() -> None:
    """The CDK stack's MONEYHUB_TOKEN_PARAMETER_PREFIX must match the Python
    backend's fallback URI template in backend.common.moneyhub_tokens, since
    CDK's parameter ARN scoping and the backend's default storage URI must
    agree on where per-owner token blobs live (see #5338, extending the
    _COVERED_STACK_PREFIX_CONSTANTS pattern from PR #5318 to this stack)."""
    backend_common = resolve_app_root() / "backend" / "common"
    if not backend_common.is_dir():
        pytest.skip(
            "backend/common is unavailable; set ALLOTMINT_APP_ROOT to the application checkout"
        )
    moneyhub_tokens_path = backend_common / "moneyhub_tokens.py"
    backend_uri_template = _fallback_string_literal(moneyhub_tokens_path, "_DEFAULT_URI_TEMPLATE")

    assert backend_uri_template == f"ssm://{MONEYHUB_TOKEN_PARAMETER_PREFIX}/{{owner}}", (
        "backend.common.moneyhub_tokens._DEFAULT_URI_TEMPLATE "
        f"('{backend_uri_template}') has drifted from CDK's "
        f"MONEYHUB_TOKEN_PARAMETER_PREFIX ('{MONEYHUB_TOKEN_PARAMETER_PREFIX}')"
    )


# Every module-level *_PREFIX string constant in moneyhub_token_store.py that is
# duplicated in a backend fallback literal must have a corresponding cross-check
# test above (see #5338, extending the pattern audited for backend_lambda_stack.py
# in PR #5318/#4933).
_COVERED_STACK_PREFIX_CONSTANTS = frozenset({"MONEYHUB_TOKEN_PARAMETER_PREFIX"})


def test_no_uncovered_duplicated_prefix_constants_in_moneyhub_token_store() -> None:
    """Guards against a future *_PREFIX constant in moneyhub_token_store.py
    being added without a matching cross-check test against its backend
    duplicate (or an explicit acknowledgement that it isn't duplicated)."""
    stack_path = CDK_DIR / "stacks" / "moneyhub_token_store.py"
    tree = ast.parse(stack_path.read_text(encoding="utf-8"))

    declared_prefix_constants = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id.endswith("_PREFIX")
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }

    assert declared_prefix_constants == _COVERED_STACK_PREFIX_CONSTANTS, (
        "Module-level *_PREFIX string constants in moneyhub_token_store.py "
        f"({sorted(declared_prefix_constants)}) no longer match the audited/covered "
        f"set ({sorted(_COVERED_STACK_PREFIX_CONSTANTS)}). Add a cross-check test "
        "for any new constant that duplicates a backend fallback literal, or "
        "update _COVERED_STACK_PREFIX_CONSTANTS if it's confirmed out of scope."
    )
