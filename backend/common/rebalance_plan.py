"""Asset-class drift and trade planning for the rebalance page (#9446).

Given an owner portfolio (as built by ``build_owner_portfolio``) and an
:class:`~backend.common.allocation_policy.AllocationPolicy`, this module

* buckets every priced holding into an asset class (literal cash holdings are
  the ``cash`` class; holdings with no recognised class are ``unclassified``),
  or into a sub-class for a class the policy targets by sub-class (#9543): a
  holding whose sub-class is unknown stays under its parent class key, with
  no target, and is reported in the notes,
* reports per-class drift against the targets, flagging classes outside the
  tolerance band,
* suggests trades that only bring *out-of-band* classes back to target, and
  never move money between accounts: each account's buys are funded only by
  its own sells and its own deployable cash,
* optionally allocates a new cash contribution to one account, buys only,
  filling the most underweight classes first.

All amounts are GBP (``market_value_gbp``); nothing here mixes currencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from backend.common.allocation_policy import AllocationPolicy
from backend.common.instrument_classification import ASSET_CLASS_LABELS, ASSET_CLASSES, CASH, normalise_asset_class
from backend.common.portfolio_loader import ACCOUNT_STEM_KEY
from backend.common.sector_labels import is_cash_instrument
from backend.common.sub_asset_class import SUB_ASSET_CLASS_LABELS, SUB_ASSET_CLASS_PARENT, SUB_ASSET_CLASSES
from backend.common.ticker_utils import split_ticker

UNCLASSIFIED = "unclassified"
#: Suggestions smaller than this (GBP) are dropped as dust.
MIN_TRADE_GBP = 1.0


@dataclass
class AccountBucket:
    """One account's priced holdings grouped by asset class."""

    id: str
    label: str
    # Literal cash (CASH.<ccy>) only; money-market funds classified as cash
    # are in class_values["cash"] but must be sold before they can fund buys.
    cash: float = 0.0
    class_values: dict[str, float] = field(default_factory=dict)
    # asset class -> {ticker: value}, used for ticker hints on trades
    class_tickers: dict[str, dict[str, float]] = field(default_factory=dict)
    literal_cash_tickers: set[str] = field(default_factory=set)
    # ticker -> display name, shown alongside ticker hints on trades
    ticker_names: dict[str, str] = field(default_factory=dict)

    def add(self, asset_class: str, ticker: str, value: float, name: str | None = None) -> None:
        self.class_values[asset_class] = self.class_values.get(asset_class, 0.0) + value
        tickers = self.class_tickers.setdefault(asset_class, {})
        tickers[ticker] = tickers.get(ticker, 0.0) + value
        if name and ticker not in self.ticker_names:
            self.ticker_names[ticker] = name

    @property
    def cash_fund_value(self) -> float:
        """Value classified as cash that is a sellable instrument (e.g. a money-market fund)."""
        return max(self.class_values.get(CASH, 0.0) - self.cash, 0.0)

    def ticker_hint(self, asset_class: str) -> str | None:
        tickers = {
            t: v for t, v in self.class_tickers.get(asset_class, {}).items() if t not in self.literal_cash_tickers
        }
        if not tickers:
            return None
        return max(tickers.items(), key=lambda item: (item[1], item[0]))[0]


@dataclass
class Holdings:
    accounts: list[AccountBucket]
    unpriced: list[str]
    #: Asset classes bucketed by sub-class rather than as a whole.
    split: frozenset[str] = frozenset()

    @property
    def total(self) -> float:
        return sum(sum(a.class_values.values()) for a in self.accounts)

    def class_total(self, asset_class: str) -> float:
        return sum(a.class_values.get(asset_class, 0.0) for a in self.accounts)

    def class_tickers(self, asset_class: str) -> list[str]:
        return sorted({t for a in self.accounts for t in a.class_tickers.get(asset_class, {})})


def split_classes(policy: AllocationPolicy) -> frozenset[str]:
    """Asset classes the policy targets by sub-class."""

    return frozenset(SUB_ASSET_CLASS_PARENT[k] for k in policy.targets if k in SUB_ASSET_CLASS_PARENT)


def _holding_value(holding: Mapping[str, Any]) -> float | None:
    raw = holding.get("market_value_gbp")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _holding_class(holding: Mapping[str, Any], ticker: str, split: frozenset[str]) -> str:
    """Bucket key: the asset class, or its sub-class when that class is split.

    A holding of a split class with no recognised sub-class keeps the parent
    key so it is still counted (and reported) rather than dropped.
    """
    if is_cash_instrument(ticker, holding.get("instrument_type")):
        return CASH
    asset_class = normalise_asset_class(holding.get("asset_class")) or UNCLASSIFIED
    if asset_class not in split:
        return asset_class
    sub_class = str(holding.get("sub_asset_class") or "").strip().lower()
    return sub_class if SUB_ASSET_CLASS_PARENT.get(sub_class) == asset_class else asset_class


def _account_id(account: Mapping[str, Any], seen: set[str]) -> str:
    """Return the account's stable id: its file stem, never its list position.

    The id goes to the frontend and comes back on a later request (the new-cash
    plan), so a position-based id could point at a different account if the
    order changed in between (#9496). Callers must build the portfolio with
    ``include_account_stem=True``; a missing or repeated stem is a bug, so it
    raises rather than falling back to the index.
    """
    stem = account.get(ACCOUNT_STEM_KEY)
    if not isinstance(stem, str) or not stem.strip():
        raise ValueError("Account has no stable id; build the portfolio with include_account_stem=True")
    account_id = stem.strip()
    if account_id in seen:
        raise ValueError(f"Duplicate account id {account_id!r}")
    seen.add(account_id)
    return account_id


def bucket_holdings(portfolio: Mapping[str, Any], split: frozenset[str] = frozenset()) -> Holdings:
    """Group the portfolio's priced holdings by account and asset class.

    Classes in ``split`` are bucketed by sub-class instead (see
    :func:`split_classes`).
    """

    accounts: list[AccountBucket] = []
    unpriced: set[str] = set()
    seen_ids: set[str] = set()
    for index, account in enumerate(portfolio.get("accounts") or []):
        label = str(account.get("account_type") or f"Account {index + 1}")
        bucket = AccountBucket(id=_account_id(account, seen_ids), label=label)
        for holding in account.get("holdings") or []:
            ticker = str(holding.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            value = _holding_value(holding)
            if value is None:
                unpriced.add(ticker)
                continue
            if value <= 0:
                continue
            asset_class = _holding_class(holding, ticker, split)
            name = str(holding.get("name") or "").strip() or None
            bucket.add(asset_class, ticker, value, name)
            if is_cash_instrument(ticker, holding.get("instrument_type")):
                bucket.cash += value
                bucket.literal_cash_tickers.add(ticker)
        accounts.append(bucket)
    return Holdings(accounts=accounts, unpriced=sorted(unpriced), split=split)


def _pct(value: float, total: float) -> float:
    return value / total * 100.0 if total > 0 else 0.0


def _bucket_keys(split: frozenset[str]) -> list[str]:
    """Every bucket key in display order.

    A split class lists its sub-classes, then its own key, which holds the
    members with no known sub-class.
    """

    keys: list[str] = []
    for asset_class in ASSET_CLASSES:
        if asset_class in split:
            keys.extend(SUB_ASSET_CLASSES[asset_class])
        keys.append(asset_class)
    return keys


def _key_label(key: str, split: frozenset[str]) -> str:
    if key in SUB_ASSET_CLASS_LABELS:
        return SUB_ASSET_CLASS_LABELS[key]
    label = ASSET_CLASS_LABELS.get(key, key)
    return f"{label} — no sub-class" if key in split else label


def _drift_row(holdings: Holdings, policy: AllocationPolicy, key: str) -> dict[str, Any]:
    value = holdings.class_total(key)
    current_pct = _pct(value, holdings.total)
    # A split class's own key only holds members with no known sub-class:
    # it has no target, like the unclassified bucket.
    targeted = bool(policy.targets) and key not in holdings.split
    target_pct = policy.targets.get(key, 0.0) if targeted else None
    drift = current_pct - target_pct if target_pct is not None else None
    return {
        "asset_class": key,
        "parent": SUB_ASSET_CLASS_PARENT.get(key, key if key in holdings.split else None),
        "label": _key_label(key, holdings.split),
        "current_value": round(value, 2),
        "current_pct": round(current_pct, 2),
        "target_pct": target_pct,
        "drift_pct": round(drift, 2) if drift is not None else None,
        "in_band": abs(drift) <= policy.tolerance_pct if drift is not None else None,
    }


def class_drift(holdings: Holdings, policy: AllocationPolicy) -> list[dict[str, Any]]:
    """Per-bucket current vs target weight, ordered by the canonical class list.

    ``parent`` is set on sub-class rows (and on a split class's "no
    sub-class" row) and is ``None`` on whole-class rows.
    """

    held = {c for a in holdings.accounts for c in a.class_values}
    keys = [k for k in _bucket_keys(holdings.split) if k in held or k in policy.targets]
    return [_drift_row(holdings, policy, key) for key in keys]


def sub_class_breakdown(portfolio: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Current value and weight of every held sub-class, whatever the policy.

    Lets the target editor show current sub-class weights before any
    sub-class target is set.
    """

    holdings = bucket_holdings(portfolio, frozenset(SUB_ASSET_CLASSES))
    rows = class_drift(holdings, AllocationPolicy())
    return [
        {k: row[k] for k in ("asset_class", "parent", "label", "current_value", "current_pct")}
        for row in rows
        if row["parent"] is not None
    ]


def _class_deltas(holdings: Holdings, policy: AllocationPolicy) -> dict[str, float]:
    """GBP change needed per out-of-band non-cash class (positive = buy)."""

    total = holdings.total
    deltas: dict[str, float] = {}
    for row in class_drift(holdings, policy):
        asset_class = row["asset_class"]
        if asset_class == CASH or row["in_band"] is not False:
            continue
        deltas[asset_class] = policy.targets.get(asset_class, 0.0) / 100.0 * total - holdings.class_total(asset_class)
    return deltas


def _trade(account: AccountBucket, asset_class: str, action: str, amount: float) -> dict[str, Any]:
    ticker = account.ticker_hint(asset_class)
    return {
        "account_id": account.id,
        "account": account.label,
        "asset_class": asset_class,
        "action": action,
        "amount": round(amount, 2),
        "ticker": ticker,
        "name": account.ticker_names.get(ticker) if ticker else None,
    }


def _sell_trades(holdings: Holdings, deltas: Mapping[str, float]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Spread each overweight class's sale across accounts pro rata to holdings."""

    trades: list[dict[str, Any]] = []
    proceeds: dict[str, float] = {}
    for asset_class, delta in deltas.items():
        held = holdings.class_total(asset_class)
        if delta >= 0 or held <= 0:
            continue
        for account in holdings.accounts:
            amount = -delta * account.class_values.get(asset_class, 0.0) / held
            if amount >= MIN_TRADE_GBP:
                trades.append(_trade(account, asset_class, "sell", amount))
                proceeds[account.id] = proceeds.get(account.id, 0.0) + amount
    return trades, proceeds


def _cash_funding(
    holdings: Holdings, policy: AllocationPolicy, deltas: Mapping[str, float], proceeds: Mapping[str, float]
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Fund buys from the cash class above its target, per account.

    Literal cash is spent first, pro rata to each account's cash. Cash-class
    funds (money-market) are sold only for whatever buys sales and literal
    cash still leave unfunded, pro rata to each account's fund holdings.
    """

    excess = holdings.class_total(CASH) - policy.targets.get(CASH, 0.0) / 100.0 * holdings.total
    if excess <= 0:
        return {}, []
    funding: dict[str, float] = {}
    total_literal = sum(a.cash for a in holdings.accounts)
    from_literal = min(excess, total_literal)
    for account in holdings.accounts:
        if account.cash > 0:
            funding[account.id] = from_literal * account.cash / total_literal

    total_funds = sum(a.cash_fund_value for a in holdings.accounts)
    still_needed = sum(d for d in deltas.values() if d > 0) - sum(proceeds.values()) - from_literal
    to_sell = min(excess - from_literal, max(still_needed, 0.0), total_funds)
    trades: list[dict[str, Any]] = []
    for account in holdings.accounts if to_sell >= MIN_TRADE_GBP else []:
        amount = to_sell * account.cash_fund_value / total_funds
        if amount >= MIN_TRADE_GBP:
            trades.append(_trade(account, CASH, "sell", amount))
            funding[account.id] = funding.get(account.id, 0.0) + amount
    return funding, trades


def _buy_trades(
    holdings: Holdings, deltas: Mapping[str, float], funding: Mapping[str, float]
) -> tuple[list[dict[str, Any]], float]:
    """Fund underweight classes inside each account from that account's pool."""

    needed = {c: d for c, d in deltas.items() if d > 0}
    total_need = sum(needed.values())
    total_funding = sum(funding.values())
    if total_need <= 0 or total_funding <= 0:
        return [], max(total_need, 0.0)
    scale = min(1.0, total_funding / total_need)
    trades: list[dict[str, Any]] = []
    for account in holdings.accounts:
        share = funding.get(account.id, 0.0) / total_funding
        for asset_class, need in needed.items():
            amount = need * scale * share
            if amount >= MIN_TRADE_GBP:
                trades.append(_trade(account, asset_class, "buy", amount))
    return trades, max(total_need - total_funding, 0.0)


def suggest_account_trades(holdings: Holdings, policy: AllocationPolicy) -> dict[str, Any]:
    """Per-account trades that bring out-of-band classes back to target.

    Within each account, buys never exceed that account's sell proceeds plus
    its share of cash above the cash target. Literal cash is never sold;
    a cash-class fund is sold only when it is needed to fund buys.
    """

    if not policy.targets or holdings.total <= 0:
        return {"trades": [], "unfunded_amount": 0.0}
    deltas = _class_deltas(holdings, policy)
    sells, proceeds = _sell_trades(holdings, deltas)
    cash_funding, fund_sells = _cash_funding(holdings, policy, deltas, proceeds)
    funding = dict(proceeds)
    for account_id, amount in cash_funding.items():
        funding[account_id] = funding.get(account_id, 0.0) + amount
    buys, unfunded = _buy_trades(holdings, deltas, funding)
    return {"trades": sells + fund_sells + buys, "unfunded_amount": round(unfunded, 2)}


def _water_fill(gaps: Mapping[str, float], amount: float) -> dict[str, float]:
    """Split ``amount`` across positive ``gaps``, largest gaps first.

    Finds the level ``L`` where ``sum(max(gap - L, 0)) == amount`` so the most
    underweight classes are topped up first and end equally underweight.
    """

    ordered = sorted(((c, g) for c, g in gaps.items() if g > 0), key=lambda item: (-item[1], item[0]))
    if not ordered or amount <= 0:
        return {}
    running = 0.0
    level = 0.0
    count = len(ordered)
    for index, (_, gap) in enumerate(ordered):
        running += gap
        level = (running - amount) / (index + 1)
        next_gap = ordered[index + 1][1] if index + 1 < count else -math.inf
        if level >= next_gap:
            break
    level = max(level, 0.0)
    return {c: g - level for c, g in ordered if g - level > 0}


def suggest_new_cash(holdings: Holdings, policy: AllocationPolicy, amount: float, account_id: str) -> dict[str, Any]:
    """Buy-only allocation of a new ``amount`` paid into ``account_id``."""

    if not policy.targets:
        raise ValueError("Set target allocations before planning a contribution")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("New cash amount must be a positive number")
    account = next((a for a in holdings.accounts if a.id == account_id), None)
    if account is None:
        raise ValueError(f"Unknown account {account_id!r}")

    new_total = holdings.total + amount
    gaps = {c: pct / 100.0 * new_total - holdings.class_total(c) for c, pct in policy.targets.items()}
    allocation = _water_fill(gaps, amount)
    buys = [_trade(account, c, "buy", value) for c, value in allocation.items() if c != CASH and value >= MIN_TRADE_GBP]
    kept = amount - sum(t["amount"] for t in buys)
    return {"account_id": account.id, "account": account.label, "trades": buys, "keep_as_cash": round(kept, 2)}


def _cash_after_trades(holdings: Holdings, trades: Iterable[Mapping[str, Any]]) -> float:
    # Selling a cash-class fund only moves value within the cash class.
    net_sold = sum(t["amount"] if t["action"] == "sell" else -t["amount"] for t in trades if t["asset_class"] != CASH)
    return holdings.class_total(CASH) + net_sold


def _notes(holdings: Holdings, policy: AllocationPolicy, trades: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    unclassified = holdings.class_total(UNCLASSIFIED)
    if unclassified > 0:
        notes.append(
            f"£{unclassified:,.2f} ({_pct(unclassified, holdings.total):.2f}%) is in holdings with no asset class; "
            "classify them so drift reflects your whole portfolio."
        )
    for asset_class in sorted(holdings.split, key=ASSET_CLASSES.index):
        value = holdings.class_total(asset_class)
        if value > 0:
            notes.append(
                f"£{value:,.2f} of {ASSET_CLASS_LABELS[asset_class]} holdings "
                f"({', '.join(holdings.class_tickers(asset_class))}) has no sub-class and is not traded; "
                "set sub_asset_class in the instrument metadata or classification overrides."
            )
    if holdings.unpriced:
        notes.append(f"No GBP value for {', '.join(holdings.unpriced)}; excluded from drift and trades.")
    unfunded = trades["unfunded_amount"]
    if unfunded > 0:
        notes.append(f"£{unfunded:,.2f} of buys could not be funded from sales and spare cash in the same account.")
    if policy.targets and holdings.total > 0:
        cash_pct = _pct(_cash_after_trades(holdings, trades["trades"]), holdings.total)
        if cash_pct - policy.targets.get(CASH, 0.0) > policy.tolerance_pct:
            notes.append(
                f"Cash would still be {cash_pct:.2f}% of the portfolio, above its band; "
                "use the new-cash planner to decide where to deploy it."
            )
    return notes


def unclassified_holdings(holdings: Holdings) -> list[dict[str, Any]]:
    """Holdings in the unclassified bucket, largest first, for the classify page (#9495).

    ``symbol``/``exchange`` address the instrument metadata the asset class is
    saved to; ``exchange`` is ``None`` when the ticker carries no suffix.
    """

    values: dict[str, float] = {}
    names: dict[str, str] = {}
    for account in holdings.accounts:
        for ticker, value in account.class_tickers.get(UNCLASSIFIED, {}).items():
            values[ticker] = values.get(ticker, 0.0) + value
            if ticker in account.ticker_names:
                names.setdefault(ticker, account.ticker_names[ticker])
    rows = []
    for ticker, value in sorted(values.items(), key=lambda item: (-item[1], item[0])):
        symbol, exchange = split_ticker(ticker)
        rows.append(
            {
                "ticker": ticker,
                "symbol": symbol,
                "exchange": exchange,
                "name": names.get(ticker),
                "value": round(value, 2),
            }
        )
    return rows


def build_plan(portfolio: Mapping[str, Any], policy: AllocationPolicy) -> dict[str, Any]:
    """Drift table, per-account trades and notes for one owner."""

    holdings = bucket_holdings(portfolio, split_classes(policy))
    drift = class_drift(holdings, policy)
    trades = suggest_account_trades(holdings, policy)
    unclassified = holdings.class_total(UNCLASSIFIED)
    return {
        "policy": policy.to_dict(),
        "total_value": round(holdings.total, 2),
        "classes": drift,
        "sub_classes": sub_class_breakdown(portfolio),
        "unclassified_value": round(unclassified, 2),
        "unclassified_pct": round(_pct(unclassified, holdings.total), 2),
        "unclassified_holdings": unclassified_holdings(holdings),
        "unpriced_tickers": holdings.unpriced,
        "accounts": [
            {"id": a.id, "label": a.label, "value": round(sum(a.class_values.values()), 2), "cash": round(a.cash, 2)}
            for a in holdings.accounts
        ],
        "trades": trades["trades"],
        "unfunded_amount": trades["unfunded_amount"],
        "notes": _notes(holdings, policy, trades),
    }
