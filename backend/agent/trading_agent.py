from __future__ import annotations

"""Simple trading agent that generates signals from recent price moves."""

import logging
from typing import Dict, Iterable, List, Optional

import pandas as pd

from backend.common import prices
from backend.common.alerts import publish_alert

logger = logging.getLogger(__name__)


PRICE_DROP_THRESHOLD = -5.0  # percent
PRICE_GAIN_THRESHOLD = 5.0   # percent


def _price_column(df: pd.DataFrame) -> Optional[str]:
    """Return the first recognised price column name in ``df``."""
    for col in ("close", "Close", "close_gbp", "Close_gbp"):
        if col in df.columns:
            return col
    return None


def generate_signals(snapshot: Dict[str, Dict]) -> List[Dict]:
    """Create trade signals from a price snapshot.

    Currently emits a BUY signal if the price has risen more than
    ``PRICE_GAIN_THRESHOLD`` over the last week and a SELL signal if the
    price has fallen by more than ``PRICE_DROP_THRESHOLD``.
    """
    signals: List[Dict] = []
    for ticker, info in snapshot.items():
        change = info.get("change_7d_pct")
        if change is None:
            continue
        if change <= PRICE_DROP_THRESHOLD:
            signals.append(
                {
                    "ticker": ticker,
                    "action": "SELL",
                    "reason": f"Price dropped {change:.2f}% in last 7d",
                }
            )
        elif change >= PRICE_GAIN_THRESHOLD:
            signals.append(
                {
                    "ticker": ticker,
                    "action": "BUY",
                    "reason": f"Price gained {change:.2f}% in last 7d",
                }
            )
    return signals


def run(tickers: Optional[Iterable[str]] = None) -> List[Dict]:
    """Refresh prices, generate signals and publish alerts.

    Args:
        tickers: optional iterable of ticker symbols.  If provided, price
            history is loaded only for these tickers using
            :func:`prices.load_prices_for_tickers`.  Otherwise the full
            portfolio universe is refreshed via :func:`prices.refresh_prices`.

    Returns:
        A list of generated signals.
    """
    if tickers:
        df = prices.load_prices_for_tickers(tickers, days=60)
        snapshot: Dict[str, Dict] = {}
        for tkr in tickers:
            tdf = df[df["Ticker"] == tkr]
            if tdf.empty:
                continue
            col = _price_column(tdf)
            if col is None:
                continue
            last = float(tdf[col].iloc[-1])
            change_7d_pct: Optional[float] = None
            if len(tdf) > 6:
                prev = float(tdf[col].iloc[-6])
                if prev not in (0.0, None):
                    change_7d_pct = (last / prev - 1.0) * 100.0
            snapshot[tkr] = {
                "last_price": last,
                "change_7d_pct": change_7d_pct,
                "change_30d_pct": None,
            }
    else:
        snapshot = prices.refresh_prices().get("snapshot", {})

    signals = generate_signals(snapshot)
    for sig in signals:
        alert = {
            "ticker": sig["ticker"],
            "action": sig["action"],
            "reason": sig["reason"],
            "message": f"{sig['action']} {sig['ticker']}: {sig['reason']}",
        }
        publish_alert(alert)
        logger.info("Published alert: %s", alert)
    return signals


if __name__ == "__main__":  # pragma: no cover
    run()
