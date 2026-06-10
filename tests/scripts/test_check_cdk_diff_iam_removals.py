"""Unit tests for scripts/check_cdk_diff_iam_removals.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_cdk_diff_iam_removals.py"
spec = importlib.util.spec_from_file_location("check_cdk_diff_iam_removals", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
find_unmatched_allow_removals = _mod.find_unmatched_allow_removals
main = _mod.main

NO_IAM_CHANGES_DIFF = """
Stack BackendLambdaStack
Resources
[~] AWS::Lambda::Function PriceRefreshLambda
 └─ [~] Code
"""

REMOVED_DEPLOY_ROLE_GRANT_DIFF = """
Stack BackendLambdaStack
IAM Statement Changes
┌───┬──────────────────────┬────────┬───────────────────────┬──────────────────────────┐
│   │ Resource              │ Effect │ Action                │ Principal                 │
├───┼──────────────────────┼────────┼───────────────────────┼──────────────────────────┤
│ - │ ${PriceRefreshAlias}  │ Allow  │ lambda:InvokeFunction │ AWS:${github-deploy.Arn} │
└───┴──────────────────────┴────────┴───────────────────────┴──────────────────────────┘

Resources
[-] AWS::IAM::Policy GithubDeployRoleForLambdaInvokePolicy80453C0D destroy
"""

REPLACED_DEPLOY_ROLE_GRANT_DIFF = """
Stack BackendLambdaStack
IAM Statement Changes
┌───┬──────────────────────┬────────┬───────────────────────┬──────────────────────────┐
│   │ Resource              │ Effect │ Action                │ Principal                 │
├───┼──────────────────────┼────────┼───────────────────────┼──────────────────────────┤
│ - │ ${PriceRefreshAlias}  │ Allow  │ lambda:InvokeFunction │ AWS:${github-deploy.Arn} │
│ + │ ${PriceRefreshAlias}  │ Allow  │ lambda:InvokeFunction │ AWS:${github-deploy.Arn} │
└───┴──────────────────────┴────────┴───────────────────────┴──────────────────────────┘
"""

REMOVED_UNRELATED_GRANT_DIFF = """
Stack BackendLambdaStack
IAM Statement Changes
┌───┬──────────────────────┬────────┬───────────────────────┬──────────────────────────┐
│   │ Resource              │ Effect │ Action                │ Principal                 │
├───┼──────────────────────┼────────┼───────────────────────┼──────────────────────────┤
│ - │ ${SomeOtherBucket}    │ Allow  │ s3:GetObject          │ AWS:${SomeOtherRole.Arn} │
└───┴──────────────────────┴────────┴───────────────────────┴──────────────────────────┘
"""

REMOVED_DENY_DIFF = """
Stack BackendLambdaStack
IAM Statement Changes
┌───┬──────────────────────┬────────┬───────────────────────┬──────────────────────────┐
│   │ Resource              │ Effect │ Action                │ Principal                 │
├───┼──────────────────────┼────────┼───────────────────────┼──────────────────────────┤
│ - │ ${PortfolioDataBucket}│ Deny   │ s3:DeleteObject       │ AWS:${github-deploy.Arn} │
└───┴──────────────────────┴────────┴───────────────────────┴──────────────────────────┘
"""


def test_no_iam_table_means_no_removals() -> None:
    assert find_unmatched_allow_removals(NO_IAM_CHANGES_DIFF) == []


def test_flags_removed_allow_grant_for_deploy_role() -> None:
    unmatched = find_unmatched_allow_removals(REMOVED_DEPLOY_ROLE_GRANT_DIFF)
    assert len(unmatched) == 1
    assert "lambda:InvokeFunction" in unmatched[0]


def test_replace_pair_is_not_flagged() -> None:
    assert find_unmatched_allow_removals(REPLACED_DEPLOY_ROLE_GRANT_DIFF) == []


def test_removed_grant_for_unrelated_role_is_not_flagged() -> None:
    assert find_unmatched_allow_removals(REMOVED_UNRELATED_GRANT_DIFF) == []


def test_removed_deny_statement_is_not_flagged() -> None:
    assert find_unmatched_allow_removals(REMOVED_DENY_DIFF) == []


def test_main_returns_zero_for_clean_diff(tmp_path) -> None:
    diff_file = tmp_path / "diff.txt"
    diff_file.write_text(REPLACED_DEPLOY_ROLE_GRANT_DIFF, encoding="utf-8")
    assert main(["check_cdk_diff_iam_removals.py", str(diff_file)]) == 0


def test_main_returns_one_for_removed_grant(tmp_path) -> None:
    diff_file = tmp_path / "diff.txt"
    diff_file.write_text(REMOVED_DEPLOY_ROLE_GRANT_DIFF, encoding="utf-8")
    assert main(["check_cdk_diff_iam_removals.py", str(diff_file)]) == 1
