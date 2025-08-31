"""Helpers for sending trading alerts via SNS or Telegram."""

from __future__ import annotations

import logging
import csv
import os
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd

from backend.common import prices, compliance
from backend.common.alerts import publish_alert
from backend import alerts as alert_utils
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    list_all_unique_tickers,
    compute_owner_performance,
)
from backend.common.trade_metrics import (
    TRADE_LOG_PATH,
    load_and_compute_metrics,
)
from backend.config import config
from backend.utils.telegram_utils import send_message, redact_token

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
        try:
            publish_alert({"message": message})
        except RuntimeError:
            logger.info("SNS topic ARN not configured; skipping publish")
        alert_utils.send_push_notification(message)

    if (
        os.getenv("TELEGRAM_BOT_TOKEN")
        and os.getenv("TELEGRAM_CHAT_ID")
        and config.app_env != "aws"
    ):
        try:
            send_message(message)
        except Exception as exc:  # pragma: no cover - network errors are rare
            logger.warning("Telegram send failed: %s", redact_token(str(exc)))

PRICE_DROP_THRESHOLD = -5.0  # percent
PRICE_GAIN_THRESHOLD = 5.0   # percent
DRAWDOWN_ALERT_THRESHOLD = 0.2  # 20% decline; set to 0 to disable


def _compute_rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """Return the RSI for ``series`` or ``None`` if insufficient data."""
    if len(series) <= period:
        return None
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period).mean()
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _price_column(df: pd.DataFrame) -> Optional[str]:
    """Return the first recognised price column name in ``df``."""
    for col in ("close", "Close", "close_gbp", "Close_gbp"):
        if col in df.columns:
            return col
    return None


def generate_signals(snapshot: Dict[str, Dict]) -> List[Dict]:
    """Create trade signals from a price snapshot.

    Signals are generated using a combination of price momentum over the last
    week, relative strength index (RSI) and simple moving averages (SMA). The
    first matching condition for a ticker is used to determine the action.
    """
    signals: List[Dict] = []
    for ticker, info in snapshot.items():
        change = info.get("change_7d_pct")
        if change is not None:
            if change <= PRICE_DROP_THRESHOLD:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "SELL",
                        "reason": f"Price dropped {change:.2f}% in last 7d",
                    }
                )
                continue
            if change >= PRICE_GAIN_THRESHOLD:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "BUY",
                        "reason": f"Price gained {change:.2f}% in last 7d",
                    }
                )
                continue

        rsi = info.get("rsi")
        if rsi is not None:
            if rsi > 70:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "SELL",
                        "reason": f"RSI {rsi:.2f} above 70",
                    }
                )
                continue
            if rsi < 30:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "BUY",
                        "reason": f"RSI {rsi:.2f} below 30",
                    }
                )
                continue

        short_ma = info.get("sma_50")
        long_ma = info.get("sma_200")
        if short_ma is not None and long_ma is not None:
            if short_ma > long_ma:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "BUY",
                        "reason": f"50d MA {short_ma:.2f} above 200d MA {long_ma:.2f}",
                    }
                )
            elif short_ma < long_ma:
                signals.append(
                    {
                        "ticker": ticker,
                        "action": "SELL",
                        "reason": f"50d MA {short_ma:.2f} below 200d MA {long_ma:.2f}",
                    }
                )
    return signals


  
def _log_trade(ticker: str, action: str, price: float, ts: Optional[datetime] = None) -> None:
    """Append a trade record to the trade log.

    The log is stored as CSV at :data:`backend.common.trade_metrics.TRADE_LOG_PATH`.
    """

    ts = ts or datetime.utcnow()
    header = not TRADE_LOG_PATH.exists()
    TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        if max_dd is None or not (-1.0 <= max_dd <= 0.0):
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

    # Compliance check before any trading activity
    for pf in list_portfolios():
        owner = pf.get("owner", "")
        result = compliance.check_owner(owner)
        if result.get("warnings"):
            logger.warning("Compliance warnings for %s: %s", owner, result["warnings"])
            return []

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
        rsi = _compute_rsi(tdf[col])
        sma_50 = tdf[col].rolling(window=50).mean().iloc[-1] if len(tdf) >= 50 else None
        sma_200 = tdf[col].rolling(window=200).mean().iloc[-1] if len(tdf) >= 200 else None
        snapshot[tkr] = {
            "last_price": last,
            "change_7d_pct": change_7d_pct,
            "change_30d_pct": None,
            "rsi": rsi,
            "sma_50": float(sma_50) if sma_50 is not None and not pd.isna(sma_50) else None,
            "sma_200": float(sma_200) if sma_200 is not None and not pd.isna(sma_200) else None,
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
