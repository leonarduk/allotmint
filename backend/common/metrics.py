from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.compliance import load_transactions
from backend.common import portfolio as portfolio_mod


METRICS_DIR = Path(__file__).resolve().parents[2] / "data" / "metrics"


@dataclass
class PositionPeriod:
    ticker: str
    open: date
    close: Optional[date]


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val)).date()
    except Exception:
        return None


def position_periods(owner: str, txs: Optional[List[Dict[str, Any]]] = None) -> List[PositionPeriod]:
    """Return open/close periods for each fully closed position.

    Positions still open have ``close`` set to ``None``.
    """
    txs = txs or load_transactions(owner)
    ledgers: Dict[str, Dict[str, Any]] = {}
    periods: List[PositionPeriod] = []
    for t in txs:
        ticker = (t.get("ticker") or "").upper()
        action = (t.get("type") or t.get("kind") or "").lower()
        d = _parse_date(t.get("date"))
        qty = float(t.get("shares") or t.get("quantity") or 0)
        if not ticker or not d or action not in {"buy", "purchase", "sell"}:
            continue
        pos = ledgers.get(ticker)
        if action in {"buy", "purchase"}:
            if pos:
                pos["qty"] += qty
            else:
                ledgers[ticker] = {"open": d, "qty": qty}
        elif action == "sell" and pos:
            pos["qty"] -= qty
            if pos["qty"] <= 0:
                periods.append(PositionPeriod(ticker, pos["open"], d))
                ledgers.pop(ticker, None)
    for tkr, pos in ledgers.items():
        periods.append(PositionPeriod(tkr, pos["open"], None))
    return periods


def calculate_portfolio_turnover(
    owner: str,
    txs: Optional[List[Dict[str, Any]]] = None,
    portfolio_value: Optional[float] = None,
) -> float:
    """Estimate portfolio turnover ratio for ``owner``.

    ``portfolio_value`` can be provided directly for tests; otherwise the
    current value is loaded from the owner portfolio snapshot.
    """
    txs = txs or load_transactions(owner)
    trade_value = 0.0
    for t in txs:
        action = (t.get("type") or t.get("kind") or "").lower()
        if action not in {"buy", "purchase", "sell"}:
            continue
        amt_minor = float(t.get("amount_minor") or 0)
        trade_value += abs(amt_minor) / 100.0
    if portfolio_value is None:
        try:
            pf = portfolio_mod.build_owner_portfolio(owner)
            portfolio_value = float(pf.get("total_value_estimate_gbp") or 0.0)
        except FileNotFoundError:
            portfolio_value = 0.0
    if not portfolio_value:
        return 0.0
    return trade_value / portfolio_value


def calculate_average_holding_period(
    owner: str,
    txs: Optional[List[Dict[str, Any]]] = None,
    *,
    as_of: Optional[date] = None,
) -> float:
    """Average holding period in days for all positions.

    Open positions are measured up to ``as_of`` (defaults to today).
    """
    as_of = as_of or date.today()
    periods = position_periods(owner, txs)
    days: List[int] = []
    for p in periods:
        end = p.close or as_of
        days.append((end - p.open).days)
    if not days:
        return 0.0
    return sum(days) / len(days)


def _metrics_path(owner: str) -> Path:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    return METRICS_DIR / f"{owner}_metrics.json"


def load_metrics(owner: str) -> Dict[str, Any] | None:
    path = _metrics_path(owner)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def compute_and_store_metrics(
    owner: str,
    txs: Optional[List[Dict[str, Any]]] = None,
    *,
    as_of: Optional[date] = None,
    portfolio_value: Optional[float] = None,
) -> Dict[str, Any]:
    metrics = {
        "owner": owner,
        "as_of": (as_of or date.today()).isoformat(),
        "turnover": calculate_portfolio_turnover(owner, txs, portfolio_value=portfolio_value),
        "average_holding_period": calculate_average_holding_period(owner, txs, as_of=as_of),
    }
    _metrics_path(owner).write_text(json.dumps(metrics))
    return metrics

