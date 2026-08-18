"""Stub for the tax-allowance engine, which lives in the private
``allotmint-pro`` package. See :mod:`backend.common.core_optional` for the
degradation pattern routes should use around this import.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE, missing_package

try:
    from allotmint_pro.allowances import (  # noqa: F401
        current_tax_year,
        load_yearly_contributions,
        remaining_allowances,
    )
except ModuleNotFoundError as exc:
    if not missing_package(exc):
        raise
    raise ModuleNotFoundError(f"backend.common.allowances requires allotmint-pro. {UPGRADE_MESSAGE}") from exc
