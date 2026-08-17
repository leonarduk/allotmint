"""Stub for the VaR/Sharpe risk engine, which lives in the private
``allotmint-pro`` package. See :mod:`backend.common.core_optional` for the
degradation pattern routes should use around this import.
"""

from __future__ import annotations

from backend.common.core_optional import UPGRADE_MESSAGE

try:
    from allotmint_pro.risk import (  # noqa: F401
        compute_portfolio_var,
        compute_portfolio_var_breakdown,
        compute_portfolio_var_scenarios,
        compute_sharpe_ratio,
    )
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(f"backend.common.risk requires allotmint-pro. {UPGRADE_MESSAGE}") from exc
