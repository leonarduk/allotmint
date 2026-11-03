"""Find decisions worth logging and pre-fill their facts (#10481).

Nothing here writes. A draft carries the facts of the change (instrument,
amount, weights before and after, a context snapshot) and suggested legs for
the later review; ``reason`` is always blank because the owner writes the
reasoning. A draft reaches the plan only through
:func:`backend.decision_journal.entries.confirm_decision`, on the owner's
explicit confirmation.

Context is gathered through :class:`ContextTools`, which only accepts the
read-only tools in :data:`READ_ONLY_CONTEXT_TOOLS`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import pandas as pd

from backend.common.core_optional import missing_package
from backend.common.holdings_rebuild import transaction_quantity
from backend.common.investment_plan import InvestmentPlan
from backend.decision_journal.prices import SeriesLoader, load_return_series
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

#: The only tools capture may call. All of them read; none writes anywhere.
READ_ONLY_CONTEXT_TOOLS: frozenset[str] = frozenset(
    {
        "get_live_prices",
        "get_instrument_technicals",
        "get_instrument_valuation",
        "get_allocation",
        "get_trend_watch_flag",
    }
)
#: Trade types that can qualify for a prompt.
QUALIFYING_TRADE_TYPES = frozenset({"BUY", "SELL"})
#: The daily run lists unlogged trades from this far back.
LOOKBACK_DAYS = 30
_TECHNICALS_WINDOW_DAYS = 400
#: ticker -> valuation profile (``allotmint_pro.screener.valuation.instrument_valuation``).
ValuationLoader = Callable[[str], Any]
#: Valuation-profile sections and the fields of each a snapshot keeps.
_VALUATION_FIELDS: dict[str, tuple[str, ...]] = {
    "valuation": ("pe_ratio", "forward_pe", "pb_ratio", "ev_ebitda"),
    "income": ("dividend_yield", "payout_ratio"),
    "nav": ("premium_discount", "status"),
}


class ContextTools:
    """Named context providers, restricted to :data:`READ_ONLY_CONTEXT_TOOLS`."""

    def __init__(self, providers: Mapping[str, Callable[..., Any]]):
        refused = sorted(set(providers) - READ_ONLY_CONTEXT_TOOLS)
        if refused:
            raise ValueError(f"Not read-only context tools: {', '.join(refused)}")
        self._providers = dict(providers)

    def call(self, name: str, **kwargs: Any) -> Any:
        """The provider's result, or ``None`` when no provider is configured for ``name``."""
        if name not in READ_ONLY_CONTEXT_TOOLS:
            raise PermissionError(f"{name} is not a read-only context tool")
        provider = self._providers.get(name)
        return None if provider is None else provider(**kwargs)


def new_decision_id() -> str:
    return f"dj-{uuid.uuid4().hex[:12]}"


def trade_amount_gbp(tx: Mapping[str, Any]) -> Optional[float]:
    """``|units * price_gbp|`` for a trade, or ``None`` when either is missing.

    Units come from :func:`transaction_quantity`, so a Portfolio Performance
    row's fixed-point ``shares`` (real units x 10^8) is scaled down (#11222).
    """
    units = transaction_quantity(tx)
    price = tx.get("price_gbp")
    if units is None or price is None:
        return None
    return round(abs(float(units) * float(price)), 2)


def _tx_date(tx: Mapping[str, Any]) -> Optional[date]:
    try:
        return date.fromisoformat(str(tx.get("date") or "")[:10])
    except ValueError:
        return None


def qualifying_trades(
    transactions: Iterable[Mapping[str, Any]],
    *,
    threshold_gbp: float,
    handled_refs: set[str],
    since: date,
    until: date,
) -> list[dict[str, Any]]:
    """BUY/SELL trades of at least ``threshold_gbp`` in ``[since, until]`` not yet logged or dismissed."""
    found = []
    for tx in transactions:
        change = trade_change(tx)
        if change is None or change["source_ref"] in handled_refs or change["amount_gbp"] < threshold_gbp:
            continue
        if since <= date.fromisoformat(change["date"]) <= until:
            found.append(change)
    return sorted(found, key=lambda change: change["date"], reverse=True)


def trade_change(tx: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """The facts of a dated, priced BUY/SELL with an id; ``None`` for anything else."""
    kind = str(tx.get("type") or "").upper()
    day, amount, ref = _tx_date(tx), trade_amount_gbp(tx), tx.get("id")
    if kind not in QUALIFYING_TRADE_TYPES or not tx.get("ticker") or not ref or day is None or amount is None:
        return None
    return {
        "source_ref": ref,
        "date": day.isoformat(),
        "type": kind,
        "ticker": str(tx["ticker"]).upper(),
        "account": tx.get("account"),
        "amount_gbp": amount,
        "price_gbp": tx.get("price_gbp"),
    }


def lookback_window(as_of: date) -> tuple[date, date]:
    return as_of - timedelta(days=LOOKBACK_DAYS), as_of


def plan_class_of(plan: Optional[InvestmentPlan], ticker: str) -> Optional[str]:
    """The plan class whose vehicles name ``ticker``, if any."""
    if plan is None:
        return None
    for asset_class, vehicles in plan.vehicles.items():
        if any((v.ticker or "").upper() == ticker.upper() for v in vehicles):
            return asset_class
    return None


def _weights(change: Mapping[str, Any], allocation: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Weight of the ticker now and before the trade, estimated from current holdings.

    A trade moves money between the holding and the account's cash, so the
    total is unchanged and the earlier value is the current one plus (SELL)
    or minus (BUY) the trade amount. When that comes out negative (a BUY
    larger than what is held now, e.g. after a later sale or a price fall),
    the current holdings can't give the earlier weight, so ``before_pct`` is
    ``None`` rather than a clamped 0%.
    """
    total = float((allocation or {}).get("total_value_gbp") or 0.0)
    if total <= 0:
        return {"before_pct": None, "after_pct": None, "basis": "no holdings valuation available"}
    held = float((allocation or {}).get("values_gbp", {}).get(change["ticker"], 0.0))
    sign = 1 if change["type"] == "SELL" else -1
    before = held + sign * float(change["amount_gbp"])
    return {
        "before_pct": round(before / total * 100, 2) if before >= 0 else None,
        "after_pct": round(held / total * 100, 2),
        "basis": "current holdings; before = current value adjusted by the trade amount",
    }


def _suggested_legs(change: Mapping[str, Any]) -> list[dict[str, Any]]:
    ticker = change["ticker"]
    if change["type"] == "SELL":
        return [
            {"role": "chosen", "label": "Proceeds held as cash", "ticker": None},
            {"role": "alternative", "label": f"Keep holding {ticker}", "ticker": ticker},
        ]
    return [
        {"role": "chosen", "label": f"Bought {ticker}", "ticker": ticker},
        {"role": "alternative", "label": "Keep the cash", "ticker": None},
    ]


def trade_draft(
    change: Mapping[str, Any],
    tools: ContextTools,
    *,
    plan: Optional[InvestmentPlan] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """A pre-filled, unsaved draft for a qualifying trade (see :func:`qualifying_trades`)."""
    ticker, amount = change["ticker"], float(change["amount_gbp"])
    verb = "Sold" if change["type"] == "SELL" else "Bought"
    snapshot = {
        "taken_on": (today or date.today()).isoformat(),
        "instrument": ticker,
        "trade_type": change["type"],
        "trade_date": change["date"],
        "amount_gbp": amount,
        "price_gbp_at_trade": change.get("price_gbp"),
        "plan_class": plan_class_of(plan, ticker),
        "weights": _weights(change, tools.call("get_allocation")),
        "latest_prices": tools.call("get_live_prices", tickers=[ticker]),
        "technicals": tools.call("get_instrument_technicals", ticker=ticker),
        "valuation": tools.call("get_instrument_valuation", ticker=ticker),
        "trend_watch": tools.call("get_trend_watch_flag", ticker=ticker, on=change["date"]),
    }
    legs = _suggested_legs(change)
    return {
        "id": new_decision_id(),
        "kind": "trade",
        "source_ref": change["source_ref"],
        "date": change["date"],
        "decision": f"{verb} £{amount:,.0f} of {ticker}",
        "alternatives": [leg["label"] for leg in legs if leg["role"] == "alternative"],
        "reason": "",
        "amount_gbp": amount,
        "legs": legs,
        "snapshot": {key: value for key, value in snapshot.items() if value is not None},
    }


def _pct(value: float) -> str:
    return f"{value:g}%"


def plan_change_draft(
    previous: Mapping[str, float], current: Mapping[str, float], *, on: Optional[date] = None
) -> Optional[dict[str, Any]]:
    """A draft for a change of plan target weights, or ``None`` when the targets are unchanged."""
    classes = sorted(set(previous) | set(current))
    changes: list[dict[str, Any]] = [
        {"class": key, "before_pct": previous.get(key, 0.0), "after_pct": current.get(key, 0.0)}
        for key in classes
        if abs(previous.get(key, 0.0) - current.get(key, 0.0)) > 1e-9
    ]
    if not changes:
        return None
    day = (on or date.today()).isoformat()
    described = ", ".join(f"{c['class']} {_pct(c['before_pct'])} → {_pct(c['after_pct'])}" for c in changes)
    return {
        "id": new_decision_id(),
        "kind": "plan_change",
        "source_ref": None,
        "date": day,
        "decision": f"Changed plan target: {described}",
        "alternatives": ["Keep the previous target"],
        "reason": "",
        "amount_gbp": None,
        "legs": [],
        "snapshot": {"taken_on": day, "target_before": dict(previous), "target_after": dict(current)},
    }


def _technicals(ticker: str, load_series: SeriesLoader, today: date) -> Optional[dict[str, Any]]:
    """Trailing returns and distance from the 200-day average, from stored closes."""
    closes, basis = load_series(ticker, today - timedelta(days=_TECHNICALS_WINDOW_DAYS), today)
    if len(closes) < 2:
        return None
    last = float(closes.iloc[-1])

    def trailing(days: int) -> Optional[float]:
        earlier = closes[closes.index <= pd.Timestamp(today - timedelta(days=days))]
        return None if earlier.empty else round((last / float(earlier.iloc[-1]) - 1) * 100, 2)

    average = float(closes.tail(200).mean())
    return {
        "as_of": closes.index[-1].date().isoformat(),
        "return_basis": basis,
        "return_3m_pct": trailing(91),
        "return_12m_pct": trailing(365),
        "pct_vs_200d_avg": round((last / average - 1) * 100, 2),
    }


def _latest_prices(tickers: list[str], load_series: SeriesLoader, today: date) -> dict[str, Any]:
    prices = {}
    for ticker in tickers:
        closes, _basis = load_series(ticker, today - timedelta(days=14), today)
        prices[ticker] = None if closes.empty else round(float(closes.iloc[-1]), 4)
    return prices


def _allocation(owner: str, accounts_root: Optional[Path]) -> dict[str, Any]:
    from backend.common.portfolio import build_owner_portfolio

    portfolio = build_owner_portfolio(owner, accounts_root)
    values: dict[str, float] = {}
    for account in portfolio.get("accounts", []):
        for holding in account.get("holdings", []):
            ticker = str(holding.get("ticker") or "").upper()
            if ticker:
                values[ticker] = values.get(ticker, 0.0) + float(holding.get("market_value_gbp") or 0.0)
    # The portfolio total includes holdings without a ticker (e.g. cash).
    return {"total_value_gbp": round(float(portfolio.get("total_value_estimate_gbp") or 0.0), 2), "values_gbp": values}


def trend_watch_flag(report: Optional[Mapping[str, Any]], ticker: str, on: str) -> Optional[dict[str, Any]]:
    """Whether ``report`` (a trend-watch run, #10476) listed ``ticker`` as flagged.

    ``None`` when there is no report or it was run after ``on`` (the trade
    date): a later run says nothing about what the list showed at the time.
    """
    if report is None:
        return None
    run_date = str(report.get("run_date") or "")
    if not run_date or run_date > on:
        return None
    flagged = any(str(item.get("ticker") or "").upper() == ticker.upper() for item in report.get("items") or [])
    return {"flagged": flagged, "report_date": run_date}


def _latest_trend_watch(owner: str) -> Optional[dict[str, Any]]:
    """The owner's latest trend-watch report, or ``None`` when there is none or it can't be read.

    The flag is optional context for a draft, so a storage failure (an S3
    AccessDenied, an unreadable document, ...) leaves it unknown rather than
    aborting capture (#11270). Only the read is guarded.
    """
    from backend.trend_watch import storage

    try:
        return storage.load_latest(owner)
    except storage.InvalidOwner:
        return None  # an owner id trend watch cannot store under has no reports
    except Exception as exc:
        logger.warning(
            "Could not read the latest trend-watch report for %s (%s); leaving the flag unknown",
            sanitise_log_value(owner),
            sanitise_log_value(type(exc).__name__),
        )
        return None


def _pro_valuation_loader() -> Optional[ValuationLoader]:
    """The screener's valuation profile, or ``None`` without allotmint-pro installed."""
    try:
        from allotmint_pro.screener.valuation import instrument_valuation
    except ModuleNotFoundError as exc:
        if not missing_package(exc):
            raise
        return None
    return instrument_valuation


def _valuation_block(profile: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """The multiples, income and NAV figures of a valuation profile; ``None`` when it has none."""
    block: dict[str, Any] = {}
    for section, fields in _VALUATION_FIELDS.items():
        values = profile.get(section) or {}
        prefix = "nav_" if section == "nav" else ""
        block.update({f"{prefix}{key}": values.get(key) for key in fields if values.get(key) is not None})
    if not block:
        return None
    quality = profile.get("data_quality") or {}
    extra = {"price": profile.get("price"), "price_currency": profile.get("price_currency")}
    extra["price_as_of"] = quality.get("price_last_date")
    return {**block, **{key: value for key, value in extra.items() if value is not None}}


def _valuation(ticker: str, load: ValuationLoader) -> Optional[dict[str, Any]]:
    """A compact valuation block for ``ticker``, or ``None`` when there is no data or it can't be read.

    Valuation is optional context, so a provider failure leaves it out of the
    snapshot rather than blocking the draft.
    """
    try:
        profile = load(ticker)
    except Exception as exc:  # noqa: BLE001 - optional context; the draft goes ahead without it
        logger.warning(
            "Could not load the valuation for %s (%s); leaving it out of the snapshot",
            sanitise_log_value(ticker),
            sanitise_log_value(type(exc).__name__),
        )
        return None
    data = profile.model_dump() if hasattr(profile, "model_dump") else profile
    return _valuation_block(data) if isinstance(data, Mapping) else None


def default_context_tools(
    owner: str,
    accounts_root: Optional[Path],
    *,
    load_series: SeriesLoader = load_return_series,
    load_valuation: Optional[ValuationLoader] = None,
    today: Optional[date] = None,
) -> ContextTools:
    """Local read-only providers.

    ``get_instrument_valuation`` reads the screener's valuation profile
    (``load_valuation``, defaulting to allotmint-pro's); without one it has no
    provider, so the snapshot carries no valuation.
    """
    day = today or date.today()
    providers: dict[str, Callable[..., Any]] = {
        "get_allocation": lambda: _allocation(owner, accounts_root),
        "get_live_prices": lambda tickers: _latest_prices(tickers, load_series, day),
        "get_instrument_technicals": lambda ticker: _technicals(ticker, load_series, day),
        "get_trend_watch_flag": lambda ticker, on: trend_watch_flag(_latest_trend_watch(owner), ticker, on),
    }
    valuation_loader = load_valuation or _pro_valuation_loader()
    if valuation_loader is not None:
        providers["get_instrument_valuation"] = lambda ticker: _valuation(ticker, valuation_loader)
    return ContextTools(providers)
