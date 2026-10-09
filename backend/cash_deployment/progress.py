"""Was each tranche carried out? Schedule vs actual for a cash deployment (#10480).

Read-only: it matches the account's own BUY transactions against each
tranche's window, from its due date up to (not including) the next tranche's
due date. Callers pass only the schedule's account's transactions, so BUYs in
other accounts never count, and nothing before ``start_date`` falls in any
window. All amounts are pence (``*_minor``).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Optional

from backend.cash_deployment.schedule import ScheduleInput, due_dates, tranche_amounts, window_end
from backend.common.holdings_rebuild import transaction_quantity

BUY_TYPES = frozenset({"BUY", "PURCHASE"})
INTEREST_TYPES = frozenset({"INTEREST"})
#: A tranche is done once this share of it is invested (leaves room for dealing costs and rounding).
DONE_RATIO = 0.99


def _tx_date(tx: Mapping[str, Any]) -> Optional[date]:
    try:
        return date.fromisoformat(str(tx.get("date") or "")[:10])
    except ValueError:
        return None


def _float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def buy_value_minor(tx: Mapping[str, Any]) -> int:
    """Pence spent on a BUY: ``amount_minor`` when recorded, else price x units + fees (0 if unknown)."""
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor:
        return round(abs(amount_minor))
    price, qty = _float(tx.get("price_gbp")), transaction_quantity(tx)
    if price is None or qty is None:
        return 0
    return round((abs(price * qty) + (_float(tx.get("fees")) or 0.0)) * 100)


def _typed(transactions: Iterable[Mapping[str, Any]], types: frozenset[str]) -> list[tuple[date, Mapping[str, Any]]]:
    rows = []
    for tx in transactions:
        tx_date = _tx_date(tx)
        if tx_date is not None and str(tx.get("type") or "").strip().upper() in types:
            rows.append((tx_date, tx))
    return rows


def _status(amount: int, invested: int, due: date, end: date, as_of: date) -> str:
    if as_of < due:
        return "upcoming"
    if invested >= amount * DONE_RATIO:
        return "done"
    closed = as_of >= end
    if invested > 0:
        return "partly_done"
    return "skipped" if closed else "due"


def tranche_rows(
    schedule: ScheduleInput, transactions: Iterable[Mapping[str, Any]], as_of: date
) -> list[dict[str, Any]]:
    """Per tranche: due date, window end, planned and invested pence, and status."""
    buys = _typed(transactions, BUY_TYPES)
    rows = []
    for index, (due, amount) in enumerate(zip(due_dates(schedule), tranche_amounts(schedule))):
        end = window_end(schedule, index)
        invested = sum(buy_value_minor(tx) for tx_date, tx in buys if due <= tx_date < end and tx_date <= as_of)
        rows.append(
            {
                "index": index,
                "due_date": due.isoformat(),
                "window_end": end.isoformat(),
                "amount_minor": amount,
                "invested_minor": invested,
                "status": _status(amount, invested, due, end, as_of),
                "overdue": as_of >= end and invested < amount * DONE_RATIO,
            }
        )
    return rows


def interest_minor(schedule: ScheduleInput, transactions: Iterable[Mapping[str, Any]], as_of: date) -> int:
    """Interest credited to the account from ``start_date`` to ``as_of``, in pence."""
    total = 0.0
    for tx_date, tx in _typed(transactions, INTEREST_TYPES):
        if schedule.start_date <= tx_date <= as_of:
            total += abs(_float(tx.get("amount_minor")) or 0.0)
    return round(total)


def _gbp(minor: int) -> str:
    return f"£{minor / 100:,.2f}"


def drift_summary(overdue: int, in_cash: int, planned_in_cash: int) -> str:
    """A factual one-liner on the schedule vs actual; no advice."""
    if overdue:
        noun = "tranche" if overdue == 1 else "tranches"
        return f"{overdue} {noun} overdue, {_gbp(in_cash)} still in cash vs {_gbp(planned_in_cash)} planned"
    return f"On schedule: {_gbp(in_cash)} still in cash vs {_gbp(planned_in_cash)} planned"


def current_tranche(rows: list[dict[str, Any]], as_of: date) -> Optional[dict[str, Any]]:
    """The tranche whose window contains ``as_of`` and is not yet done, if any."""
    today = as_of.isoformat()
    for row in rows:
        if row["due_date"] <= today < row["window_end"] and row["status"] in {"due", "partly_done"}:
            return row
    return None


def build_progress(schedule: ScheduleInput, transactions: Iterable[Mapping[str, Any]], as_of: date) -> dict[str, Any]:
    """Deployed vs remaining, schedule vs actual, overdue count and interest earned."""
    txs = list(transactions)
    rows = tranche_rows(schedule, txs, as_of)
    deployed = sum(r["invested_minor"] for r in rows)
    planned = sum(r["amount_minor"] for r in rows if r["due_date"] <= as_of.isoformat())
    total = schedule.total_amount_minor
    in_cash, planned_in_cash = max(total - deployed, 0), max(total - planned, 0)
    overdue = sum(1 for r in rows if r["overdue"])
    return {
        "as_of": as_of.isoformat(),
        "tranches": rows,
        "total_amount_minor": total,
        "deployed_minor": deployed,
        "remaining_minor": in_cash,
        "planned_to_date_minor": planned,
        "planned_remaining_minor": planned_in_cash,
        "overdue_count": overdue,
        "interest_minor": interest_minor(schedule, txs, as_of),
        "current": current_tranche(rows, as_of),
        "summary": drift_summary(overdue, in_cash, planned_in_cash),
    }
