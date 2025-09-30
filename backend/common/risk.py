"""Risk metrics helpers.

This module currently exposes :func:`compute_portfolio_var` which calculates
historical-simulation Value-at-Risk (VaR) for a portfolio owner.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from backend.common import portfolio_utils
from backend.common import portfolio as portfolio_mod
from backend.config import config


def compute_portfolio_var(
    owner: str, days: int = 365, confidence: float = 0.95, include_cash: bool = True
) -> Dict:
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
        Confidence level for the VaR quantile. Accepts either a decimal
        fraction between 0 and 1 or a percentage in the range 0–100. For
        example, ``0.95`` and ``95`` are treated equivalently. Values close
        to 95 % and 99 % are commonly used.
    include_cash:
        Whether to include cash holdings when reconstructing the portfolio
        history. Set to ``False`` to exclude cash from the return series.

    Returns
    -------
    Dict
        ``{"window_days": int, "confidence": float, "1d": float | None, "10d": float | None}``

    Raises
    ------
    ValueError
        If ``days`` is not positive or ``confidence`` is outside the accepted
        ranges.
    FileNotFoundError
        If the owner does not exist.
    """

    if days <= 0:
        raise ValueError("days must be positive")

    # Allow the confidence level to be expressed as a percentage (e.g. 95)
    # or as a decimal fraction (0.95). Convert percentages to a fraction and
    # validate the result.
    if 0 < confidence < 1:
        pass
    elif 1 <= confidence <= 100 and float(confidence).is_integer():
        confidence = confidence / 100
    else:
        raise ValueError("confidence must be between 0 and 1 or 0 and 100")

    # exclude any instruments flagged in the price snapshot until refreshed
    perf = portfolio_utils.compute_owner_performance(
        owner,
        days=days + 1,
        include_flagged=False,
        include_cash=include_cash,
    )
    history = perf.get("history", []) if isinstance(perf, dict) else perf
    if not history:
        return {"window_days": days, "confidence": confidence, "1d": None, "10d": None}

    df = pd.DataFrame(history[-(days + 1) :])
    returns = df["daily_return"].dropna()
    if len(returns) > days:
        returns = returns.iloc[-days:]
    if returns.empty:
        return {"window_days": days, "confidence": confidence, "1d": None, "10d": None}

    current_value = float(df["value"].iloc[-1])

    quantile_1d = returns.quantile(1 - confidence)
    if pd.isna(quantile_1d):
        var_1d = None
    else:
        var_1d_loss_pct = max(-(quantile_1d), 0.0)
        var_1d = float(var_1d_loss_pct * current_value)

    ten_day_returns = returns.add(1).rolling(10).apply(np.prod) - 1
    ten_day_returns = ten_day_returns.dropna()
    if ten_day_returns.empty:
        var_10d = None
    else:
        quantile_10d = ten_day_returns.quantile(1 - confidence)
        if pd.isna(quantile_10d):
            var_10d = None
        else:
            var_10d_loss_pct = max(-(quantile_10d), 0.0)
            var_10d = float(var_10d_loss_pct * current_value)

    return {
        "window_days": days,
        "confidence": confidence,
        "1d": round(var_1d, 2) if var_1d is not None else None,
        "10d": round(var_10d, 2) if var_10d is not None else None,
    }


def compute_portfolio_var_breakdown(
    owner: str, days: int = 365, confidence: float = 0.95, include_cash: bool = True
) -> List[Dict[str, float]]:
    """Return VaR contribution for each holding in the owner's portfolio.

    The calculation loads the owner's portfolio, collapses holdings to one row
    per ticker using :func:`portfolio_utils.aggregate_by_ticker` and then
    computes the 1-day VaR for each instrument's price series.  The resulting
    per-unit VaR is scaled by the current position value to obtain the
    contribution in GBP.  Instruments for which no prices are available are
    skipped.  The returned list is sorted with the largest contributions first.

    Parameters are identical to :func:`compute_portfolio_var`.
    """

    if days <= 0:
        raise ValueError("days must be positive")

    if 0 < confidence < 1:
        pass
    elif 1 <= confidence <= 100 and float(confidence).is_integer():
        confidence = confidence / 100
    else:
        raise ValueError("confidence must be between 0 and 1 or 0 and 100")

    portfolio = portfolio_mod.build_owner_portfolio(owner)
    rows = portfolio_utils.aggregate_by_ticker(portfolio)

    breakdown: List[Dict[str, float]] = []
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        # Optionally skip cash holdings
        if not include_cash and ticker.startswith("CASH"):
            continue

        sym, exch = (ticker.rsplit(".", 1) + ["L"])[:2]
        ts = portfolio_utils.load_meta_timeseries(sym, exch, days)
        var_single = portfolio_utils.compute_var(ts, confidence=confidence)
        if var_single is None or ts is None or ts.empty:
            continue

        closes = pd.to_numeric(ts["Close"], errors="coerce").dropna()
        if closes.empty:
            continue
        last_price = float(closes.iloc[-1])
        if last_price == 0:
            continue
        # Var as a fraction of price
        var_pct = var_single / last_price

        value = row.get("market_value_gbp") or 0.0
        if not value and row.get("currency") == "GBP":
            value = float(row.get("units", 0.0)) * last_price
        if not value:
            continue

        contribution = var_pct * value
        breakdown.append({"ticker": ticker, "contribution": round(float(contribution), 2)})

    breakdown.sort(key=lambda x: x["contribution"], reverse=True)
    return breakdown


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
    if isinstance(perf, dict):
        perf = perf.get("history", [])
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
