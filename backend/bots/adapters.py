"""Adapters registering the existing scheduled jobs as bots.

Each adapter calls the job's current entry point unchanged and only turns its
return value into a :class:`RunResult` -- the job logic stays where it is. A
job that finds nothing is never reported as ``ok`` (#8805).

New agents register themselves the same way (``register_bot(MyBot())``) from
their own module, imported at the bottom of this file.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import asdict
from typing import Any, Dict, Literal, Optional

from pydantic import Field, model_validator

from backend.bots.registry import BotKind, BotRunContext, BotScope, BotSettings, RunResult, Schedule, register_bot

PENSION_REPORT_CADENCE_ENV = "PENSION_REPORT_CADENCE"


def _base_settings() -> Dict[str, Any]:
    return {"enabled": True, "cadence": "daily"}


# ─────────────────────────────── price refresh ─────────────────────────────


class PriceRefreshBot:
    id = "price-refresh"
    name = "Price refresh"
    description = "Fetches the latest prices for every held and watched ticker and writes the price snapshot."
    kind: BotKind = "job"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = BotSettings
    default_schedule: Optional[Schedule] = Schedule(hour=0)  # cdk DailyPriceRefresh
    timeout_minutes = 15

    def default_settings(self) -> Dict[str, Any]:
        return _base_settings()

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        # Looked up at call time (sys.modules), not bound at import, so tests
        # that re-import the handler module patch the function actually run.
        price_refresh = importlib.import_module("backend.lambda_api.price_refresh")
        raw = price_refresh._run_refresh()
        if not isinstance(raw, dict):
            return RunResult(status="ok", summary="Completed", raw=raw)
        if raw.get("error"):
            return RunResult(status="failed", summary="Price refresh failed", error=str(raw["error"]), raw=raw)
        tickers = list(raw.get("tickers") or [])
        unpriced = list(raw.get("unpriced") or [])
        report = {"tickers": len(tickers), "unpriced": unpriced[:100], "timestamp": raw.get("timestamp")}
        if not tickers:
            return RunResult(
                status="failed",
                summary="No tickers found: nothing was refreshed",
                report=report,
                raw=raw,
            )
        priced = len(tickers) - len(unpriced)
        summary = f"{priced} of {len(tickers)} tickers priced"
        return RunResult(status="partial" if unpriced else "ok", summary=summary, report=report, raw=raw)


# ───────────────────────────── dividend refresh ────────────────────────────


class DividendRefreshBot:
    id = "dividend-refresh"
    name = "Dividend refresh"
    description = "Records new dividend transactions for every held ticker, skipping ones already recorded."
    kind: BotKind = "job"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = BotSettings
    default_schedule: Optional[Schedule] = Schedule(hour=6)  # cdk DailyDividendRefresh
    timeout_minutes = 15

    def default_settings(self) -> Dict[str, Any]:
        return _base_settings()

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        from backend.common.dividends import refresh_dividends

        raw = refresh_dividends()
        created = int(raw.get("dividends_created") or 0)
        accounts = int(raw.get("accounts_processed") or 0)
        skipped = list(raw.get("skipped_tickers") or [])
        report = {
            "dividends_created": created,
            "accounts_processed": accounts,
            "tickers_processed": raw.get("tickers_processed"),
            "skipped_tickers": skipped[:100],
        }
        if accounts == 0:
            return RunResult(status="partial", summary="No accounts with holdings found", report=report, raw=raw)
        return RunResult(
            status="ok",
            summary=f"{created} dividends recorded across {accounts} accounts",
            report=report,
            raw=raw,
        )


# ────────────────────────────── pension report ─────────────────────────────


class PensionReportSettings(BotSettings):
    cadence: Literal["weekly", "monthly"] = "monthly"


def _pension_rule_cadence() -> str:
    cadence = os.getenv(PENSION_REPORT_CADENCE_ENV, "monthly")
    return cadence if cadence in ("weekly", "monthly") else "monthly"


class PensionReportBot:
    id = "pension-report"
    name = "Pension report"
    description = "Emails each owner a pension forecast, year-to-date return and shortfall alerts."
    kind: BotKind = "job"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = PensionReportSettings
    timeout_minutes = 10

    @property
    def default_schedule(self) -> Optional[Schedule]:
        # Mirrors cdk PensionReportRun, whose cadence is a deploy-time context value.
        if _pension_rule_cadence() == "weekly":
            return Schedule(hour=7, weekday=0)
        return Schedule(hour=7, day=1)

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": _pension_rule_cadence()}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        pension_report = importlib.import_module("backend.lambda_api.pension_report")
        raw = pension_report._run_report()
        sent = int(raw.get("sent") or 0)
        errors = [str(e) for e in raw.get("errors") or []]
        report = {"sent": sent, "errors": errors}
        if errors:
            return RunResult(
                status="partial" if sent else "failed",
                summary=f"{sent} reports sent, {len(errors)} failed",
                report=report,
                error="\n".join(errors),
                raw=raw,
            )
        if sent == 0:
            return RunResult(status="partial", summary="No reports sent (no eligible owners)", report=report, raw=raw)
        return RunResult(status="ok", summary=f"{sent} reports sent", report=report, raw=raw)


# ─────────────────────────────── trading agent ─────────────────────────────

#: The trading-agent thresholds the Bots page may edit. ``require_pro_checks``
#: is deliberately absent: it is server policy, not a user threshold.
TRADING_THRESHOLD_FIELDS = (
    "rsi_buy",
    "rsi_sell",
    "rsi_window",
    "ma_short_window",
    "ma_long_window",
    "pe_max",
    "de_max",
    "min_sharpe",
    "max_volatility",
)


class TradingAgentBotSettings(BotSettings):
    """Public, non-secret signal thresholds (same set as ``TradingAgentSettings``)."""

    rsi_buy: Optional[float] = Field(default=None, ge=0, le=100, description="RSI at or below which to BUY")
    rsi_sell: Optional[float] = Field(default=None, ge=0, le=100, description="RSI at or above which to SELL")
    rsi_window: int = Field(default=14, ge=2, le=200, description="RSI look-back (days)")
    ma_short_window: int = Field(default=20, ge=2, le=250, description="Short moving average (days)")
    ma_long_window: int = Field(default=50, ge=2, le=400, description="Long moving average (days)")
    pe_max: Optional[float] = Field(default=None, gt=0, le=1000, description="Max P/E for BUY signals")
    de_max: Optional[float] = Field(default=None, ge=0, le=100, description="Max debt/equity for BUY signals")
    min_sharpe: Optional[float] = Field(default=None, ge=-10, le=10, description="Minimum Sharpe ratio")
    max_volatility: Optional[float] = Field(default=None, gt=0, le=10, description="Max daily volatility")

    @model_validator(mode="after")
    def _check_ranges(self) -> "TradingAgentBotSettings":
        if self.rsi_buy is not None and self.rsi_sell is not None and self.rsi_buy >= self.rsi_sell:
            raise ValueError("rsi_buy must be lower than rsi_sell")
        if self.ma_short_window >= self.ma_long_window:
            raise ValueError("ma_short_window must be shorter than ma_long_window")
        return self


class TradingAgentBot:
    id = "trading-agent"
    name = "Trading agent signals"
    description = "Checks RSI and moving-average thresholds on every held ticker and sends BUY/SELL alerts."
    kind: BotKind = "rules"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = TradingAgentBotSettings
    default_schedule: Optional[Schedule] = Schedule(hour=1)  # cdk DailyTradingAgentRun
    timeout_minutes = 10

    def default_settings(self) -> Dict[str, Any]:
        from backend.agent.trading_agent import load_base_strategy_config

        base = asdict(load_base_strategy_config())
        return {**_base_settings(), **{k: base[k] for k in TRADING_THRESHOLD_FIELDS}}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        from backend.agent import trading_agent

        # notify=True is the scheduled behaviour: alerts, trade log and the
        # drawdown sweep. Thresholds come from load_strategy_config(), which
        # applies the saved bot settings.
        signals = trading_agent.run()
        rows = [{"ticker": s.get("ticker"), "action": s.get("action"), "reason": s.get("reason")} for s in signals]
        summary = f"{len(rows)} signal{'s' if len(rows) != 1 else ''} sent" if rows else "No signals"
        return RunResult(status="ok", summary=summary, report={"signals": rows}, raw=signals)


for _bot in (TradingAgentBot(), PriceRefreshBot(), DividendRefreshBot(), PensionReportBot()):
    register_bot(_bot, replace=True)

# Agents that register themselves from their own module (see the module docstring).
from backend.reconciliation import bot as _statement_reconciliation_bot  # noqa: E402,F401
