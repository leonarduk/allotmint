"""Helpers for sending trading alerts via SNS or Telegram."""

from __future__ import annotations

import csv
import logging
import os

from backend.common.alerts import publish_alert
from backend.utils.telegram_utils import send_message
from backend.config import config
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd

from backend.common import prices
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    list_all_unique_tickers,
    compute_owner_performance,
)
from backend.common.trade_metrics import (
    TRADE_LOG_PATH,
    load_and_compute_metrics,
)

logger = logging.getLogger(__name__)


def send_trade_alert(message: str, publish: bool = True) -> None:
    """Send ``message`` using the configured alert transports.

    Args:
        message: Text to send.
        publish: When ``True`` the message is passed to
            :func:`backend.common.alerts.publish_alert` for storage/SNS
            publication. Set to ``False`` when the caller has already
            published the alert and only a Telegram notification is required.

    The message is forwarded to Telegram via
    :func:`backend.utils.telegram_utils.send_message` when both
    ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` environment variables are
    present and the application is not running on AWS (``config.app_env`` is
    not ``"aws"``).
    """

    if publish:
        publish_alert({"message": message})

    if (
        os.getenv("TELEGRAM_BOT_TOKEN")
        and os.getenv("TELEGRAM_CHAT_ID")
        and config.app_env != "aws"
    ):
        try:
            send_message(message)
        except Exception as exc:  # pragma: no cover - network errors are rare
            logger.warning("Telegram send failed: %s", exc)

PRICE_DROP_THRESHOLD = -5.0  # percent
PRICE_GAIN_THRESHOLD = 5.0   # percent
DRAWDOWN_ALERT_THRESHOLD = 0.2  # 20% decline; set to 0 to disable


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


  
def _log_trade(ticker: str, action: str, price: float, ts: Optional[datetime] = None) -> None:
    """Append a trade record to the trade log.

    The log is stored as CSV at :data:`backend.common.trade_metrics.TRADE_LOG_PATH`.
    """

    ts = ts or datetime.utcnow()
    header = not TRADE_LOG_PATH.exists()
    with TRADE_LOG_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "ticker", "action", "price"]
        )
        if header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": ts.isoformat(),
                "ticker": ticker,
                "action": action,
                "price": price,
            }
        )

def _alert_on_drawdown(threshold: float = DRAWDOWN_ALERT_THRESHOLD) -> None:
    """Emit an alert if any portfolio drawdown exceeds ``threshold``."""
    if not threshold:
        return

    for pf in list_portfolios():
        owner = pf.get("owner")
        try:
            perf = compute_owner_performance(owner)
        except FileNotFoundError:
            continue
        max_dd = perf.get("max_drawdown")
        if max_dd is None:
            continue
        if abs(max_dd) >= threshold:
            send_trade_alert(
                f"{owner} portfolio drawdown {max_dd*100:.2f}% exceeds {threshold*100:.2f}%"
            )


def run(tickers: Optional[Iterable[str]] = None) -> List[Dict]:
    """Refresh prices, generate signals and publish alerts.

    Args:
        tickers: optional iterable of ticker symbols. If omitted, all
            known instruments from the current portfolios are analysed.

    Returns:
        A list of generated signals.
    """
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
        ticker = sig["ticker"]
        price = snapshot[ticker]["last_price"]
        alert = {
            "ticker": ticker,
            "action": sig["action"],
            "reason": sig["reason"],
            "message": f"{sig['action']} {ticker}: {sig['reason']}",
        }
        # When running outside AWS publish a Telegram notification too.
        send_trade_alert(alert["message"])
        logger.info("Published alert: %s", alert)
        _log_trade(ticker, sig["action"], price)

    if signals:
        metrics = load_and_compute_metrics()
        logger.info(
            "Trade metrics - win rate: %.2f%%, average P/L: %.2f",
            metrics["win_rate"] * 100,
            metrics["average_profit"],
        )
    _alert_on_drawdown()
    return signals


if __name__ == "__main__":  # pragma: no cover
    run()
