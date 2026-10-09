"""Deterministic facts for the plan-drift brief (#10475). No LLM here.

Everything a brief states as a number comes from this module: the drift table,
uninvested cash, stale evidence, whether the review is due and what changed
since the previous brief. The agent (:mod:`backend.plan_brief.agent`) is given
these facts and may only narrate them.

Drift is measured against the **plan's** target weights (in the rebalance
vocabulary, via :func:`~backend.common.investment_plan.rebalance_weights`),
using the owner's allocation-policy tolerance band. When the saved rebalance
targets differ from the plan, that disagreement is reported as its own line
rather than silently picking one.

Amounts are GBP. Holdings use ``market_value_gbp`` (already converted from
GBX/foreign prices by the portfolio builder); transaction ``amount_minor`` is
in pence and is divided by 100 here, with ``units * price_gbp`` as the fallback
for trades. Rows with no GBP amount are skipped and counted, not mixed in.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from backend.common.allocation_policy import AllocationPolicy, parse_policy
from backend.common.investment_plan import InvestmentPlan, compare_with_rebalance_targets, rebalance_weights
from backend.common.path_utils import safe_join
from backend.common.rebalance_plan import UNCLASSIFIED, bucket_holdings, class_drift, split_classes
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

#: Evidence older than this many days is reported as stale.
STALE_EVIDENCE_DAYS = 180
#: Look-back for "what changed" when there is no earlier brief.
DEFAULT_CHANGE_WINDOW_DAYS = 31
#: A holding whose unit value moved at least this much since the last brief is a "big mover".
BIG_MOVER_PCT = 10.0
#: Literal cash below this (GBP) is not reported as uninvested.
MIN_CASH_GBP = 1.0

_INFLOW_TYPES = frozenset({"DEPOSIT", "TRANSFER_IN"})
_CASH_IN_TYPES = _INFLOW_TYPES | {"SELL"}


def _round(value: float, places: int = 2) -> float:
    return round(value + 0.0, places)


# --------------------------------------------------------------------------- drift


def _plan_policy(plan: InvestmentPlan, tolerance_pct: float) -> tuple[AllocationPolicy, str]:
    """The plan target as an :class:`AllocationPolicy`, and the basis used.

    ``plan`` when the plan's classes map onto the rebalance vocabulary;
    ``plan_rolled_up`` when they only compare at top-level asset classes.
    """
    try:
        return parse_policy({"targets": rebalance_weights(plan), "tolerance_pct": tolerance_pct}), "plan"
    except ValueError as exc:
        logger.info(
            "Plan brief for %s compares rolled up to asset classes: %s",
            sanitise_log_value(plan.owner),
            sanitise_log_value(exc),
        )
        return parse_policy({"targets": plan.parent_weights(), "tolerance_pct": tolerance_pct}), "plan_rolled_up"


def _status(drift_pp: Optional[float], tolerance_pct: float) -> str:
    if drift_pp is None:
        return "untargeted"
    if abs(drift_pp) <= tolerance_pct:
        return "in_band"
    return "over" if drift_pp > 0 else "under"


def drift_table(plan: InvestmentPlan, portfolio: Mapping[str, Any], policy: AllocationPolicy) -> dict[str, Any]:
    """Actual vs plan target per class, in percentage points and GBP.

    ``drift_gbp`` is the actual value minus the target share of the total:
    positive means above target. ``status`` is ``over``/``under`` outside the
    tolerance band, ``in_band`` inside it and ``untargeted`` for held classes
    the plan gives no weight (e.g. unclassified holdings).
    """
    plan_policy, basis = _plan_policy(plan, policy.tolerance_pct)
    holdings = bucket_holdings(portfolio, split_classes(plan_policy))
    total = holdings.total
    rows = []
    for row in class_drift(holdings, plan_policy):
        key = row["asset_class"]
        target_pct = row["target_pct"]
        value = holdings.class_total(key)
        drift_gbp = value - target_pct / 100.0 * total if target_pct is not None else None
        drift_pp = (value / total * 100.0 - target_pct) if target_pct is not None and total > 0 else None
        rows.append(
            {
                "class": key,
                "label": row["label"],
                "current_value_gbp": _round(value),
                "current_pct": _round(row["current_pct"]),
                "target_pct": target_pct,
                "drift_pp": _round(drift_pp, 1) if drift_pp is not None else None,
                "drift_gbp": _round(drift_gbp) if drift_gbp is not None else None,
                "status": _status(drift_pp, plan_policy.tolerance_pct),
            }
        )
    comparison = compare_with_rebalance_targets(plan, policy)
    return {
        "basis": basis,
        "tolerance_pct": plan_policy.tolerance_pct,
        "total_value_gbp": _round(total),
        "rows": rows,
        "out_of_band": [row["class"] for row in rows if row["status"] in ("over", "under")],
        "unclassified_value_gbp": _round(holdings.class_total(UNCLASSIFIED)),
        "unpriced_tickers": holdings.unpriced,
        # Plan target vs the saved rebalance targets: a disagreement is its own line, not silently resolved.
        "rebalance_targets_match": comparison["matches"] if policy.targets else None,
        "rebalance_targets": comparison["rebalance_targets"],
    }


# --------------------------------------------------------------------------- transactions


def load_owner_transactions(accounts_root: Path, owner: str) -> list[dict[str, Any]]:
    """Every ``<owner>/*_transactions.json`` row, tagged with its ``account``. Read-only.

    Unlike ``account_scaffold.load_transactions`` this never creates files.
    An unreadable file is logged and skipped so one bad file doesn't sink the brief.
    """
    owner_dir = safe_join(Path(accounts_root), owner)
    rows: list[dict[str, Any]] = []
    for path in sorted(owner_dir.glob("*_transactions.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Plan brief skipped %s: %s", sanitise_log_value(path.name), sanitise_log_value(exc))
            continue
        if not isinstance(data, dict):
            continue
        account = str(data.get("account_type") or path.stem.replace("_transactions", ""))
        for tx in data.get("transactions") or []:
            if isinstance(tx, dict):
                rows.append({**tx, "account": account})
    return rows


def _tx_date(tx: Mapping[str, Any]) -> Optional[date]:
    try:
        return date.fromisoformat(str(tx.get("date"))[:10])
    except ValueError:
        return None


def _finite(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _tx_gbp(tx: Mapping[str, Any]) -> Optional[float]:
    """The transaction's GBP amount, or ``None`` when it has none.

    ``amount_minor`` is pence (GBP rows only). A trade recorded without it
    falls back to ``units * price_gbp``; ``price_gbp`` is already pounds per
    unit, whatever the listing's own currency.
    """
    if str(tx.get("currency") or "GBP").upper() == "GBP":
        minor = _finite(tx.get("amount_minor"))
        if minor is not None:
            return abs(minor) / 100.0
    units, price_gbp = _finite(tx.get("units")), _finite(tx.get("price_gbp"))
    if units is not None and price_gbp is not None:
        return abs(units * price_gbp)
    return None


def _tx_type(tx: Mapping[str, Any]) -> str:
    return str(tx.get("type") or tx.get("kind") or "").strip().upper()


def _is_cash_in(tx: Mapping[str, Any]) -> bool:
    kind = _tx_type(tx)
    # An in-specie TRANSFER_IN carries a ticker and brings no cash.
    return kind in _CASH_IN_TYPES and not (kind == "TRANSFER_IN" and tx.get("ticker"))


# --------------------------------------------------------------------------- cash


def _account_matches(tx_account: str, account_id: str, label: str) -> bool:
    key = tx_account.strip().lower()
    return key in (account_id.strip().lower(), label.strip().lower())


def uninvested_cash(
    portfolio: Mapping[str, Any], transactions: Iterable[Mapping[str, Any]], today: date
) -> list[dict[str, Any]]:
    """Literal cash per account and how long it has sat since the last purchase.

    ``uninvested_since`` is the earliest cash inflow (deposit, cash transfer in
    or sale) after the account's last purchase, i.e. money that has arrived and
    not been followed by any buy. ``None`` when nothing arrived after the last
    purchase, or when the account has no transactions on file.
    """
    holdings = bucket_holdings(portfolio)
    txs = list(transactions)
    rows = []
    for account in holdings.accounts:
        if account.cash < MIN_CASH_GBP:
            continue
        mine = [tx for tx in txs if _account_matches(str(tx.get("account") or ""), account.id, account.label)]
        dated = [(d, tx) for tx in mine if (d := _tx_date(tx)) is not None and d <= today]
        buys = [d for d, tx in dated if _tx_type(tx) == "BUY"]
        last_buy = max(buys) if buys else None
        inflows = sorted((d, tx) for d, tx in dated if _is_cash_in(tx) and (last_buy is None or d > last_buy))
        since = inflows[0][0] if inflows else None
        deposits = [(d, tx) for d, tx in dated if _tx_type(tx) in _INFLOW_TYPES and _is_cash_in(tx)]
        last_deposit = max(deposits, key=lambda item: item[0]) if deposits else None
        rows.append(
            {
                "account_id": account.id,
                "account": account.label,
                "cash_gbp": _round(account.cash),
                "last_purchase": last_buy.isoformat() if last_buy else None,
                "uninvested_since": since.isoformat() if since else None,
                "days_uninvested": (today - since).days if since else None,
                "last_deposit": last_deposit[0].isoformat() if last_deposit else None,
                "last_deposit_gbp": _tx_gbp(last_deposit[1]) if last_deposit else None,
                "transactions_on_file": bool(mine),
            }
        )
    return rows


# --------------------------------------------------------------------------- plan housekeeping


def stale_evidence(plan: InvestmentPlan, today: date, max_age_days: int = STALE_EVIDENCE_DAYS) -> list[dict[str, Any]]:
    """Evidence entries whose ``as_of`` is older than ``max_age_days``."""
    stale = []
    for item in plan.evidence:
        age = (today - item.as_of).days
        if age > max_age_days:
            stale.append(
                {
                    "metric": item.metric,
                    "value": item.value,
                    "as_of": item.as_of.isoformat(),
                    "age_days": age,
                    "source": item.source,
                }
            )
    return stale


def review_status(plan: InvestmentPlan, today: date) -> dict[str, Any]:
    next_review = plan.review.next_review
    due = next_review is not None and next_review <= today
    return {
        "next_review": next_review.isoformat() if next_review else None,
        "due": due,
        "days_overdue": (today - next_review).days if due and next_review else None,
        "open_questions": list(plan.open_questions),
    }


# --------------------------------------------------------------------------- changes


def holdings_snapshot(portfolio: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """Per-ticker units and GBP value, stored with each brief to find movers next time."""
    snapshot: dict[str, dict[str, float]] = {}
    for account in portfolio.get("accounts") or []:
        for holding in account.get("holdings") or []:
            ticker = str(holding.get("ticker") or "").strip().upper()
            try:
                units = float(holding.get("units") or 0.0)
                value = float(holding.get("market_value_gbp"))
            except (TypeError, ValueError):
                continue
            if not ticker or not math.isfinite(value) or not math.isfinite(units):
                continue
            entry = snapshot.setdefault(ticker, {"units": 0.0, "value_gbp": 0.0})
            entry["units"] = _round(entry["units"] + units, 6)
            entry["value_gbp"] = _round(entry["value_gbp"] + value)
    return snapshot


def _unit_value(entry: Mapping[str, Any]) -> Optional[float]:
    try:
        units = float(entry.get("units") or 0.0)
        value = float(entry.get("value_gbp") or 0.0)
    except (TypeError, ValueError):
        return None
    return value / units if units > 0 else None


def big_movers(
    current: Mapping[str, Mapping[str, Any]],
    previous: Optional[Mapping[str, Mapping[str, Any]]],
    threshold_pct: float = BIG_MOVER_PCT,
) -> list[dict[str, Any]]:
    """Holdings whose GBP value per unit moved at least ``threshold_pct`` since the previous snapshot."""
    movers = []
    for ticker, entry in sorted((current or {}).items()):
        before = (previous or {}).get(ticker)
        now_unit, before_unit = _unit_value(entry), _unit_value(before or {})
        if not now_unit or not before_unit:
            continue
        change = (now_unit / before_unit - 1.0) * 100.0
        if abs(change) >= threshold_pct:
            movers.append({"ticker": ticker, "change_pct": _round(change, 1), "value_gbp": entry.get("value_gbp")})
    return sorted(movers, key=lambda m: -abs(m["change_pct"]))


def changes_since(
    transactions: Iterable[Mapping[str, Any]],
    since: date,
    today: date,
    snapshot: Mapping[str, Mapping[str, Any]],
    previous: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """Contributions, withdrawals, purchases, sales and big movers in ``(since, today]``."""
    totals = {"contributions": 0.0, "withdrawals": 0.0, "purchases": 0.0, "sales": 0.0}
    counts = {key: 0 for key in totals}
    skipped = 0
    kinds = {"DEPOSIT": "contributions", "TRANSFER_IN": "contributions", "WITHDRAWAL": "withdrawals"}
    kinds.update({"BUY": "purchases", "SELL": "sales"})
    for tx in transactions:
        d = _tx_date(tx)
        key = kinds.get(_tx_type(tx))
        if d is None or key is None or not since < d <= today:
            continue
        if key == "contributions" and not _is_cash_in(tx):
            continue
        amount = _tx_gbp(tx)
        if amount is None:
            skipped += 1
            continue
        totals[key] += amount
        counts[key] += 1
    previous_snapshot = (previous or {}).get("holdings_snapshot")
    previous_total = ((previous or {}).get("drift") or {}).get("total_value_gbp")
    return {
        "since": since.isoformat(),
        "previous_brief": (previous or {}).get("as_of"),
        **{f"{key}_gbp": _round(value) for key, value in totals.items()},
        "counts": counts,
        "skipped_no_gbp_amount": skipped,
        "previous_total_value_gbp": previous_total,
        "big_movers": big_movers(snapshot, previous_snapshot),
    }


# --------------------------------------------------------------------------- all facts


def build_facts(
    plan: InvestmentPlan,
    portfolio: Mapping[str, Any],
    policy: AllocationPolicy,
    transactions: Sequence[Mapping[str, Any]],
    today: date,
    previous: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Every deterministic section of the brief."""
    since = None
    if previous and previous.get("as_of"):
        try:
            since = date.fromisoformat(str(previous["as_of"]))
        except ValueError:
            since = None
    since = since or today - timedelta(days=DEFAULT_CHANGE_WINDOW_DAYS)
    snapshot = holdings_snapshot(portfolio)
    return {
        "drift": drift_table(plan, portfolio, policy),
        "cash": uninvested_cash(portfolio, transactions, today),
        "stale_evidence": stale_evidence(plan, today),
        "review": review_status(plan, today),
        "changes": changes_since(transactions, since, today, snapshot, previous),
        "holdings_snapshot": snapshot,
    }
