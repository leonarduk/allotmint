"""Helpers for sending trading alerts via SNS or Telegram."""

from __future__ import annotations

import csv
import json
import logging
import math
import os
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd

from backend import alerts as alert_utils
from backend.common import prices, compliance, indicators
from backend.common.alerts import publish_alert
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    list_all_unique_tickers,
    compute_owner_performance,
)
from backend.common.trade_metrics import (
    TRADE_LOG_PATH,
    load_and_compute_metrics,
)
from backend.config import config, TradingAgentConfig
from backend.screener import screen
from backend.utils.telegram_utils import send_message, redact_token

logger = logging.getLogger(__name__)


def load_strategy_config() -> TradingAgentConfig:
    """Return the active trading strategy configuration.

    User preferences can be supplied via a ``strategy_prefs.json`` file in the
    repository root. Values in this file override those from ``config.yaml``.
    This lightweight mechanism allows storing strategy preferences in a
    database and exporting them to JSON for the agent to consume.
    """

    base = asdict(config.trading_agent)
    prefs_path = Path(config.repo_root or ".") / "strategy_prefs.json"
    if prefs_path.exists():
        try:
            data = json.loads(prefs_path.read_text())
            if isinstance(data, dict):
                allowed_keys = set(base)
                filtered = {k: v for k, v in data.items() if v is not None and k in allowed_keys}
                unknown = set(data) - allowed_keys
                if unknown:
                    logger.info("Ignoring unknown strategy preference keys: %s", ", ".join(sorted(unknown)))
                base.update(filtered)
        except Exception as exc:  # pragma: no cover - file errors are rare
            logger.warning("Failed to load strategy preferences: %s", exc)

    return TradingAgentConfig(**base)


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
    ``config.telegram_bot_token`` and ``config.telegram_chat_id`` are set and
    the application is not running on AWS (``config.app_env`` is not
    ``"aws"``).
    """

    if publish:
        try:
            publish_alert({"message": message})
        except RuntimeError:
            logger.info("SNS topic ARN not configured; skipping publish")
        alert_utils.send_push_notification(message)

    if (
        config.telegram_bot_token
        and config.telegram_chat_id
        and config.app_env != "aws"
    ):
        try:
            send_message(message)
        except Exception as exc:  # pragma: no cover - network errors are rare
            logger.warning("Telegram send failed: %s", redact_token(str(exc)))

PRICE_DROP_THRESHOLD = -5.0  # percent
PRICE_GAIN_THRESHOLD = 5.0   # percent
DRAWDOWN_ALERT_THRESHOLD = 0.2  # 20% decline; set to 0 to disable


def _price_column(df: pd.DataFrame) -> Optional[str]:
    """Return the first recognised price column name in ``df``."""
    for col in ("close", "Close", "close_gbp", "Close_gbp"):
        if col in df.columns:
            return col
    return None


def _join_with_and(items: Sequence[str]) -> str:
    """Return a human friendly phrase that joins ``items`` with commas and ``and``."""

    items = [item for item in items if item]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _average_confidence(entries: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Return the arithmetic mean of the ``confidence`` values in ``entries``."""

    values = [entry.get("confidence") for entry in entries if entry.get("confidence") is not None]
    if not values:
        return None
    return sum(values) / len(values)


def generate_signals(snapshot: Dict[str, Dict]) -> List[Dict]:
    """Create trade signals from a price snapshot.

    Signals are generated using a mix of simple price momentum,
    relative-strength index (RSI) and moving average crossovers.
    The thresholds for RSI and moving averages are configurable via
    :mod:`backend.config`. Each signal also carries a confidence score and
    a more detailed rationale to aid downstream consumers.
    """

    signals: List[Dict] = []
    cfg = load_strategy_config()
    for ticker, info in snapshot.items():
        # risk filters
        sharpe = info.get("sharpe")
        volatility = info.get("volatility")
        if (
            cfg.min_sharpe is not None
            and sharpe is not None
            and sharpe < cfg.min_sharpe
        ) or (
            cfg.max_volatility is not None
            and volatility is not None
            and volatility > cfg.max_volatility
        ):
            continue

        action_details: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        def add_reason(
            action: str,
            indicator: str,
            summary: str,
            detail: str,
            confidence: float,
        ) -> None:
            action_details[action].append(
                {
                    "indicator": indicator,
                    "summary": summary,
                    "detail": detail,
                    "confidence": confidence,
                }
            )

        # price momentum
        change = info.get("change_7d_pct")
        if change is not None:
            if change <= PRICE_DROP_THRESHOLD:
                confidence = min(1.0, abs(change) / abs(PRICE_DROP_THRESHOLD))
                add_reason(
                    "SELL",
                    "7-day price momentum",
                    "Price has fallen sharply over the last week.",
                    (
                        f"The price dropped {abs(change):.2f}% in the last 7 days,"
                        f" breaching the {abs(PRICE_DROP_THRESHOLD):.0f}% downside"
                        " momentum threshold."
                    ),
                    confidence,
                )
            elif change >= PRICE_GAIN_THRESHOLD:
                confidence = min(1.0, abs(change) / PRICE_GAIN_THRESHOLD)
                add_reason(
                    "BUY",
                    "7-day price momentum",
                    "Price has gained strongly over the last week.",
                    (
                        f"The price gained {change:.2f}% in the last 7 days,"
                        f" exceeding the {PRICE_GAIN_THRESHOLD:.0f}% momentum"
                        " trigger."
                    ),
                    confidence,
                )

        rsi = info.get("rsi")
        ma_short = info.get("ma_short")
        ma_long = info.get("ma_long")

        if rsi is not None:
            indicator_name = f"{cfg.rsi_window}-day RSI"
            if cfg.rsi_buy is not None and rsi <= cfg.rsi_buy:
                diff = cfg.rsi_buy - rsi
                confidence = min(1.0, diff / 10)  # 10 point diff -> max confidence
                add_reason(
                    "BUY",
                    indicator_name,
                    "RSI suggests the instrument is oversold.",
                    (
                        f"The {cfg.rsi_window}-day RSI is {rsi:.2f}, below"
                        f" the buy threshold of {cfg.rsi_buy:.0f}."
                    ),
                    confidence,
                )
            elif cfg.rsi_sell is not None and rsi >= cfg.rsi_sell:
                diff = rsi - cfg.rsi_sell
                confidence = min(1.0, diff / 10)
                add_reason(
                    "SELL",
                    indicator_name,
                    "RSI points to overbought conditions.",
                    (
                        f"The {cfg.rsi_window}-day RSI is {rsi:.2f}, above"
                        f" the sell threshold of {cfg.rsi_sell:.0f}."
                    ),
                    confidence,
                )
            elif rsi < 30:
                confidence = min(1.0, (30 - rsi) / 10)
                add_reason(
                    "BUY",
                    indicator_name,
                    "RSI indicates the price may be oversold.",
                    (
                        f"The {cfg.rsi_window}-day RSI is {rsi:.2f}, below"
                        " the commonly used oversold level of 30."
                    ),
                    confidence,
                )
            elif rsi > 70:
                confidence = min(1.0, (rsi - 70) / 10)
                add_reason(
                    "SELL",
                    indicator_name,
                    "RSI indicates the price may be overbought.",
                    (
                        f"The {cfg.rsi_window}-day RSI is {rsi:.2f}, above"
                        " the typical overbought level of 70."
                    ),
                    confidence,
                )

        if ma_short is not None and ma_long is not None:
            indicator_name = (
                f"{cfg.ma_short_window}- vs {cfg.ma_long_window}-day moving averages"
            )
            if ma_short > ma_long:
                add_reason(
                    "BUY",
                    indicator_name,
                    "Short-term trend is above the longer-term trend.",
                    (
                        f"The {cfg.ma_short_window}-day moving average {ma_short:.2f}"
                        f" is above the {cfg.ma_long_window}-day average"
                        f" {ma_long:.2f}, signalling bullish momentum."
                    ),
                    0.6,
                )
            elif ma_short < ma_long:
                add_reason(
                    "SELL",
                    indicator_name,
                    "Short-term trend is below the longer-term trend.",
                    (
                        f"The {cfg.ma_short_window}-day moving average {ma_short:.2f}"
                        f" is below the {cfg.ma_long_window}-day average"
                        f" {ma_long:.2f}, signalling bearish momentum."
                    ),
                    0.6,
                )

        short_ma = info.get("sma_50")
        long_ma = info.get("sma_200")
        if short_ma is not None and long_ma is not None:
            indicator_name = "50-day vs 200-day moving averages"
            if short_ma > long_ma:
                add_reason(
                    "BUY",
                    indicator_name,
                    "Medium-term trend is bullish.",
                    (
                        f"The 50-day moving average {short_ma:.2f} is above"
                        f" the 200-day moving average {long_ma:.2f},"
                        " a classic bullish signal."
                    ),
                    0.6,
                )
            elif short_ma < long_ma:
                add_reason(
                    "SELL",
                    indicator_name,
                    "Medium-term trend is bearish.",
                    (
                        f"The 50-day moving average {short_ma:.2f} is below"
                        f" the 200-day moving average {long_ma:.2f},"
                        " suggesting a bearish trend."
                    ),
                    0.6,
                )

        best_action: Optional[str] = None
        best_reasons: List[Dict[str, Any]] = []
        best_score: tuple[int, float] = (0, 0.0)
        best_confidence: Optional[float] = None

        for action, reasons in action_details.items():
            if len(reasons) < 2:
                continue
            avg_conf = _average_confidence(reasons)
            score = (len(reasons), avg_conf or 0.0)
            if score > best_score:
                best_action = action
                best_reasons = reasons
                best_score = score
                best_confidence = avg_conf

        if not best_action or not best_reasons:
            continue

        indicator_names = [reason.get("indicator", "") for reason in best_reasons]
        indicator_phrase = _join_with_and(indicator_names)
        reason_text = (
            f"{len(best_reasons)} indicators ({indicator_phrase}) support a"
            f" {best_action.lower()} opportunity."
        )
        factor_details = [reason["detail"] for reason in best_reasons]
        rationale_text = " ".join(factor_details)

        signals.append(
            {
                "ticker": ticker,
                "action": best_action,
                "reason": reason_text,
                "confidence": best_confidence,
                "rationale": rationale_text,
                "factors": factor_details,
            }
        )

    return signals


  
def _log_trade(ticker: str, action: str, price: float, ts: Optional[datetime] = None) -> None:
    """Append a trade record to the trade log.

    The log is stored as CSV at :data:`backend.common.trade_metrics.TRADE_LOG_PATH`.
    """

    ts = ts or datetime.now(UTC)
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
        except (FileNotFoundError, ValueError):
            continue
        max_dd = perf.get("max_drawdown")
        if max_dd is None or not (-1.0 <= max_dd <= 0.0):
            continue
        if abs(max_dd) >= threshold:
            send_trade_alert(
                f"{owner} portfolio drawdown {max_dd*100:.2f}% exceeds {threshold*100:.2f}%"
            )


def run(tickers: Optional[Iterable[str]] = None, *, notify: bool = True) -> List[Dict]:
    """Refresh prices, generate signals and publish alerts.

    Args:
        tickers: optional iterable of ticker symbols. If omitted, all
            known instruments from the current portfolios are analysed.
        notify: When ``True`` send notifications for any generated signals.

    Returns:
        A list of generated signals.
    """
    tickers = list(tickers) if tickers else list_all_unique_tickers()

    owners = [pf.get("owner", "") for pf in list_portfolios()]

    df = prices.load_prices_for_tickers(tickers, days=60)
    snapshot: Dict[str, Dict] = {}
    cfg = load_strategy_config()
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
        rsi = None
        if len(tdf) >= cfg.rsi_window:
            rsi_series = indicators.rsi(tdf[col], cfg.rsi_window)
            rsi_val = rsi_series.iloc[-1]
            if pd.notna(rsi_val):
                rsi = float(rsi_val)
        ma_short = None
        if len(tdf) >= cfg.ma_short_window:
            ma_short_val = indicators.sma(tdf[col], cfg.ma_short_window).iloc[-1]
            if pd.notna(ma_short_val):
                ma_short = float(ma_short_val)
        ma_long = None
        if len(tdf) >= cfg.ma_long_window:
            ma_long_val = indicators.sma(tdf[col], cfg.ma_long_window).iloc[-1]
            if pd.notna(ma_long_val):
                ma_long = float(ma_long_val)
        sma_50 = None
        if len(tdf) >= 50:
            sma_50_val = indicators.sma(tdf[col], 50).iloc[-1]
            if pd.notna(sma_50_val):
                sma_50 = float(sma_50_val)
        sma_200 = None
        if len(tdf) >= 200:
            sma_200_val = indicators.sma(tdf[col], 200).iloc[-1]
            if pd.notna(sma_200_val):
                sma_200 = float(sma_200_val)

        returns = tdf[col].pct_change().dropna()
        volatility = float(returns.std(ddof=1)) if len(returns) >= 2 else None
        sharpe = None
        if volatility and volatility > 0:
            rf = config.risk_free_rate or 0.0
            daily_rf = rf / 252
            excess = returns - daily_rf
            sharpe = float((excess.mean() / volatility) * math.sqrt(252))

        snapshot[tkr] = {
            "last_price": last,
            "change_7d_pct": change_7d_pct,
            "change_30d_pct": None,
            "rsi": rsi,
            "ma_short": ma_short,
            "ma_long": ma_long,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "volatility": volatility,
            "sharpe": sharpe,
        }

    signals = generate_signals(snapshot)

    fundamental_params: Dict[str, float] = {}
    if cfg.pe_max is not None:
        fundamental_params["pe_max"] = cfg.pe_max
    if cfg.de_max is not None:
        fundamental_params["de_max"] = cfg.de_max
    if fundamental_params and signals:
        buy_tickers = [s["ticker"] for s in signals if s["action"] == "BUY"]
        allowed: Set[str] = set()
        if buy_tickers:
            fundamentals = screen(buy_tickers, **fundamental_params)
            allowed = {f.ticker for f in fundamentals}
        signals = [
            s for s in signals if s["action"] != "BUY" or s["ticker"] in allowed
        ]
    allowed_signals: List[Dict] = []
    for sig in signals:
        blocked = False
        for owner in owners:
            trade = {
                "owner": owner,
                "ticker": sig["ticker"],
                "type": sig["action"].lower(),
                "date": date.today().isoformat(),
            }
            result = compliance.check_trade(trade)
            if result.get("warnings"):
                logger.warning(
                    "Compliance warnings for %s: %s", owner, result["warnings"]
                )
                blocked = True
                break
        if blocked:
            continue
        ticker = sig["ticker"]
        price = snapshot[ticker]["last_price"]
        alert = {
            "ticker": ticker,
            "action": sig["action"],
            "reason": sig["reason"],
            "message": f"{sig['action']} {ticker}: {sig['reason']}",
        }
        if notify:
            send_trade_alert(alert["message"])
        logger.info("Published alert: %s", alert)
        _log_trade(ticker, sig["action"], price)
        allowed_signals.append(sig)

    if allowed_signals:
        metrics = load_and_compute_metrics()
        logger.info(
            "Trade metrics - win rate: %.2f%%, average P/L: %.2f",
            metrics["win_rate"] * 100,
            metrics["average_profit"],
        )
    _alert_on_drawdown()
    return allowed_signals


if __name__ == "__main__":  # pragma: no cover
    run()
