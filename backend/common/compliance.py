"""Stub for the compliance rule engine, which lives in the private
``allotmint-pro`` package. See :mod:`backend.common.core_optional` for the
degradation pattern routes should use around this import.

Account scaffolding (``ensure_owner_scaffold``, ``load_transactions``) is
*not* part of this stub — that plumbing stays public and lives in
:mod:`backend.common.account_scaffold`. Import it from there directly.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE, missing_package

try:
    from allotmint_pro.compliance import (  # noqa: F401
        check_owner,
        check_trade,
        evaluate_trades,
    )
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    raise ModuleNotFoundError(f"backend.common.compliance requires allotmint-pro. {UPGRADE_MESSAGE}") from exc
