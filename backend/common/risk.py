"""Risk metrics helpers.

This module currently exposes :func:`compute_portfolio_var` which calculates
historical-simulation Value-at-Risk (VaR) for a portfolio owner.
"""

from __future__ import annotations

from datetime import date
from typing import Dict

import numpy as np
import pandas as pd

from backend.common import portfolio_utils
from backend.config import config


def compute_portfolio_var(owner: str, days: int = 365, confidence: float = 0.95) -> Dict:
    """Calculate 1-day and 10-day historical VaR for ``owner``.

    Parameters
    ----------
    owner:
        Portfolio owner slug.
    days:
        Number of trailing days of history to include. Must be positive.
        The portfolio value is reconstructed over this window using current
        holdings. VaR is reported for 1-day and 10-day horizons.
    confidence:
        Confidence level for the VaR quantile. Must be between 0 and 1.
        Values of 0.95 (95 %) and 0.99 (99 %) are commonly used.

    Returns
    -------
    Dict
        ``{"window_days": int, "confidence": float, "1d": float | None, "10d": float | None}``

    Raises
    ------
    ValueError
        If ``days`` is not positive or ``confidence`` is outside (0, 1).
    FileNotFoundError
        If the owner does not exist.
    """

    if days <= 0:
        raise ValueError("days must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    perf = portfolio_utils.compute_owner_performance(owner, days=days)
    if not perf:
        return {"window_days": days, "confidence": confidence, "1d": None, "10d": None}

    df = pd.DataFrame(perf)
    returns = df["daily_return"].dropna()
    if returns.empty:
        return {"window_days": days, "confidence": confidence, "1d": None, "10d": None}

    current_value = float(df["value"].iloc[-1])

    var_1d_pct = -returns.quantile(1 - confidence)
    var_1d = float(var_1d_pct * current_value) if not pd.isna(var_1d_pct) else None

    ten_day_returns = returns.add(1).rolling(10).apply(np.prod) - 1
    ten_day_returns = ten_day_returns.dropna()
    var_10d_pct = -ten_day_returns.quantile(1 - confidence) if not ten_day_returns.empty else np.nan
    var_10d = float(var_10d_pct * current_value) if not pd.isna(var_10d_pct) else None

    return {
        "window_days": days,
        "confidence": confidence,
        "1d": round(var_1d, 2) if var_1d is not None else None,
        "10d": round(var_10d, 2) if var_10d is not None else None,
    }


def compute_sharpe_ratio(owner: str, days: int = 365) -> float | None:
    """Calculate the annualised Sharpe ratio for ``owner``.

    The calculation uses the daily returns from
    :func:`portfolio_utils.compute_owner_performance` and adjusts them by the
    configured risk-free rate. Returns ``None`` when not enough data is
    available.
    """

    if days <= 0:
        raise ValueError("days must be positive")

    perf = portfolio_utils.compute_owner_performance(owner, days=days)
    if not perf:
        return None

    returns = pd.Series([r.get("daily_return") for r in perf])
    returns = returns.dropna()
    if len(returns) < 2:
        return None

    rf = config.risk_free_rate or 0.0
    trading_days = 252
    daily_rf = rf / trading_days
    excess = returns - daily_rf
    std = excess.std(ddof=1)
    if std == 0 or pd.isna(std):
        return None

    sharpe = (excess.mean() / std) * np.sqrt(trading_days)
    return round(float(sharpe), 4)
