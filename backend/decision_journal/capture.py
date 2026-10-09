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

import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import pandas as pd

from backend.common.investment_plan import InvestmentPlan
from backend.decision_journal.prices import SeriesLoader, load_return_series

#: The only tools capture may call. All of them read; none writes anywhere.
READ_ONLY_CONTEXT_TOOLS: frozenset[str] = frozenset(
    {"get_live_prices", "get_instrument_technicals", "get_instrument_valuation", "get_allocation"}
)
#: Trade types that can qualify for a prompt.
QUALIFYING_TRADE_TYPES = frozenset({"BUY", "SELL"})
#: The daily run lists unlogged trades from this far back.
LOOKBACK_DAYS = 30
_TECHNICALS_WINDOW_DAYS = 400


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
    """``|units * price_gbp|`` for a trade, or ``None`` when either is missing."""
    units, price = tx.get("units") or tx.get("shares"), tx.get("price_gbp")
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
    or minus (BUY) the trade amount.
    """
    total = float((allocation or {}).get("total_value_gbp") or 0.0)
    if total <= 0:
        return {"before_pct": None, "after_pct": None, "basis": "no holdings valuation available"}
    held = float((allocation or {}).get("values_gbp", {}).get(change["ticker"], 0.0))
    sign = 1 if change["type"] == "SELL" else -1
    before = max(held + sign * float(change["amount_gbp"]), 0.0)
    return {
        "before_pct": round(before / total * 100, 2),
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
    changes = [
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


def default_context_tools(
    owner: str,
    accounts_root: Optional[Path],
    *,
    load_series: SeriesLoader = load_return_series,
    today: Optional[date] = None,
) -> ContextTools:
    """Local read-only providers; ``get_instrument_valuation`` has none yet, so it is left out of snapshots."""
    day = today or date.today()
    return ContextTools(
        {
            "get_allocation": lambda: _allocation(owner, accounts_root),
            "get_live_prices": lambda tickers: _latest_prices(tickers, load_series, day),
            "get_instrument_technicals": lambda ticker: _technicals(ticker, load_series, day),
        }
    )
