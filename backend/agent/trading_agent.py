"""Helpers for sending trading alerts via SNS or Telegram."""

from __future__ import annotations

import logging
import os

from typing import Dict, Iterable, List, Optional

import pandas as pd

from backend.common import prices, risk
from backend.common.alerts import publish_alert
from backend.common.portfolio_utils import list_all_unique_tickers
from backend.common.portfolio_loader import list_portfolios
from backend.utils.telegram_utils import send_message

logger = logging.getLogger(__name__)


def send_trade_alert(message: str) -> None:
    """Send ``message`` using the configured alert transports.

    The alert is always passed to :func:`backend.common.alerts.publish_alert`
    which stores it and publishes to SNS when ``SNS_TOPIC_ARN`` is set.
    If both ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` are present in the
    environment, the message is also forwarded to Telegram via
    :func:`backend.utils.telegram_utils.send_message`.
    """

    publish_alert({"message": message})

    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        try:
            send_message(message)
        except Exception as exc:  # pragma: no cover - network errors are rare
            logger.warning("Telegram send failed: %s", exc)

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


def run(tickers: Optional[Iterable[str]] = None) -> Dict:
    """Refresh prices, generate signals, publish alerts and diagnostics."""

    tickers = list(tickers) if tickers else list_all_unique_tickers()

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

    diagnostics: Dict[str, float | None] = {}
    for pf in list_portfolios():
        owner = pf.get("owner")
        if not owner:
            continue
        try:
            diagnostics[owner] = risk.compute_sortino_ratio(owner)
        except Exception as exc:  # pragma: no cover - diagnostics are best-effort
            logger.warning("Sortino ratio failed for %s: %s", owner, exc)

    return {"signals": signals, "diagnostics": diagnostics}


if __name__ == "__main__":  # pragma: no cover
    run()
