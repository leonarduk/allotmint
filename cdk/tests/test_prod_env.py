"""Unit tests for the shared required-in-prod env var validation helper.

Run from the repo root:
    pip install aws-cdk-lib constructs pytest --quiet
    pytest cdk/tests/test_prod_env.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")

from aws_cdk import App, Stack  # noqa: E402
from cdk.stacks.prod_env import assert_prod_env_vars, is_truthy_context  # noqa: E402


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
def test_is_truthy_context(value, expected) -> None:
    assert is_truthy_context(value) is expected


def test_assert_prod_env_vars_raises_when_missing_in_prod(monkeypatch) -> None:
    monkeypatch.delenv("SOME_REQUIRED_VAR", raising=False)
    app = App(context={"prod": "true"})
    stack = Stack(app, "ProdMissingVarStack")
    with pytest.raises(ValueError, match="SOME_REQUIRED_VAR"):
        assert_prod_env_vars(stack, {"SOME_REQUIRED_VAR": "a test var"})


def test_assert_prod_env_vars_raises_when_empty_string_in_prod(monkeypatch) -> None:
    monkeypatch.setenv("SOME_REQUIRED_VAR", "")
    app = App(context={"prod": "true"})
    stack = Stack(app, "ProdEmptyVarStack")
    with pytest.raises(ValueError, match="SOME_REQUIRED_VAR"):
        assert_prod_env_vars(stack, {"SOME_REQUIRED_VAR": "a test var"})


def test_assert_prod_env_vars_lists_all_missing_vars(monkeypatch) -> None:
    monkeypatch.delenv("FIRST_VAR", raising=False)
    monkeypatch.delenv("SECOND_VAR", raising=False)
    app = App(context={"prod": "true"})
    stack = Stack(app, "ProdMultiMissingStack")
    with pytest.raises(ValueError, match="FIRST_VAR") as excinfo:
        assert_prod_env_vars(stack, {"FIRST_VAR": "first", "SECOND_VAR": "second"})
    assert "SECOND_VAR" in str(excinfo.value)


def test_assert_prod_env_vars_passes_when_set_in_prod(monkeypatch) -> None:
    monkeypatch.setenv("SOME_REQUIRED_VAR", "a-real-value")
    app = App(context={"prod": "true"})
    stack = Stack(app, "ProdVarSetStack")
    # Must not raise.
    assert_prod_env_vars(stack, {"SOME_REQUIRED_VAR": "a test var"})


def test_assert_prod_env_vars_noop_outside_prod(monkeypatch) -> None:
    monkeypatch.delenv("SOME_REQUIRED_VAR", raising=False)
    app = App()
    stack = Stack(app, "NonProdStack")
    # Must not raise even though the var is unset.
    assert_prod_env_vars(stack, {"SOME_REQUIRED_VAR": "a test var"})
