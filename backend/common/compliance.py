"""Stub for the compliance rule engine, which lives in the private
``allotmint-core`` package. See :mod:`backend.common.core_optional` for the
degradation pattern routes should use around this import.

Account scaffolding (``ensure_owner_scaffold``, ``load_transactions``) is
*not* part of this stub — that plumbing stays public and lives in
:mod:`backend.common.account_scaffold`. Import it from there directly.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE

try:
    from allotmint_core.compliance import (  # noqa: F401
        check_owner,
        check_trade,
        evaluate_trades,
    )
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(f"backend.common.compliance requires allotmint-core. {UPGRADE_MESSAGE}") from exc
