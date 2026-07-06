"""Shared helpers for validating required-in-prod environment variables.

Centralises the pattern introduced in StaticSiteStack (#3847, #3866): fail CDK
synthesis loudly when a variable that is only required for production deploys
is missing or empty, instead of letting CloudFormation silently omit whatever
depends on it.
"""

import os

from constructs import Construct


def is_truthy_context(value: object) -> bool:
    """Return true when a CDK context value explicitly opts into production."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def assert_prod_env_vars(scope: Construct, required_vars: dict[str, str]) -> None:
    """Raise ``ValueError`` if any required-in-prod env var is missing/empty.

    ``required_vars`` maps env var name to a short human-readable description
    used in the error message. Validation only runs when the ``prod`` CDK
    context is truthy; dev/staging synths are unaffected. See #3847, #3866,
    #4731.
    """

    if not is_truthy_context(scope.node.try_get_context("prod")):
        return

    missing = [name for name in required_vars if not os.getenv(name)]
    if not missing:
        return

    details = "; ".join(f"{name} ({required_vars[name]})" for name in missing)
    raise ValueError(f"Missing required-in-prod environment variable(s): {details}. See #3847 and #3866 for context.")
