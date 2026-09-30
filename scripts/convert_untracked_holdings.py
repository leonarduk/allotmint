"""Record holdings no transaction mentions as opening-balance transactions.

Holdings are rebuilt from each account's transactions. A holding entered by
hand before ``/input`` recorded opening balances (#8206), or imported as a
holdings snapshot, has no transactions behind it: the rebuild carries it
forward unchanged, but selling it through the transaction form finds nothing
to sell.

For every such holding this appends a ``TRANSFER_IN`` of its units to the
account's transactions file (the same record ``/input`` writes) and rebuilds
the account, so the holding's value and position come from transactions like
any other.

* Cost: ``cost_basis_gbp / units`` when the holding has a positive cost, else
  the transfer has no price and the rebuild keeps the holding's existing cost.
* Date: the holding's ``acquired_date``, else the account's oldest
  transaction, else today.
* ``--include-cash``: a ``CASH.GBP`` balance no cash transaction explains gets
  an opening ``DEPOSIT`` (a ``WITHDRAWAL`` if negative) of that amount, dated at
  the oldest transaction. Without one, the first cash row the account records
  (e.g. an imported ``DIVIDEND``) makes the rebuild replace the balance with
  that row's amount alone.
* Skipped and reported: ``CASH.GBP`` without ``--include-cash``, holdings
  without units (value-only entries need a price), and holdings files whose
  name is not lower-case (the rebuild writes the lower-case file).

Dry run by default. Running it again after ``--write`` changes nothing, since
every converted holding is then tracked.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.common.accounts_store import LocalAccountsStore, S3AccountsStore
from backend.common.holdings_rebuild import (
    CASH_TICKER,
    TRADE_CASH_FLAG,
    _tracked_instruments,
    name_aliases,
    replay_transactions,
)
from backend.config import config
from backend.routes import transactions as tx_routes

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

AccountsStore = LocalAccountsStore | S3AccountsStore


@dataclass
class AccountPlan:
    owner: str
    account: str
    transfers: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_day(value: Any) -> str | None:
    day = str(value or "")[:10]
    return day if _ISO_DATE.match(day) else None


def opening_transfers(
    transactions: Sequence[Mapping[str, Any]],
    holdings: Sequence[Mapping[str, Any]],
    *,
    include_cash: bool = False,
    trade_cash: bool = False,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Opening rows for the holdings no transaction mentions, and the ones skipped with why."""
    aliases = name_aliases(transactions, holdings)
    tracked = _tracked_instruments(transactions, aliases)
    # The rebuild's own test for "cash comes from transactions" (a cash row, or
    # a settled trade when the account opts into trade_cash_effects).
    if replay_transactions(transactions, trade_cash=trade_cash, aliases=aliases, warn=False).cash_seen:
        tracked.add(CASH_TICKER)
    dates = sorted(day for day in (_iso_day(t.get("date")) for t in transactions) if day)
    fallback_date = dates[0] if dates else date.today().isoformat()
    transfers: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    for holding in holdings:
        ticker = str(holding.get("ticker") or "").strip().upper()
        if not ticker or ticker in tracked:
            continue
        if ticker == CASH_TICKER:
            if not include_cash:
                skipped.append((ticker, "cash balance: re-run with --include-cash to record a DEPOSIT"))
            elif (deposit := _opening_cash(holding, fallback_date)) is None:
                skipped.append((ticker, "no balance to record"))
            else:
                transfers.append(deposit)
            continue
        units = _positive(holding.get("units"))
        if units is None:
            skipped.append((ticker, "no units: re-enter it on /input with units and a price"))
            continue
        transfer: dict[str, Any] = {
            "type": "TRANSFER_IN",
            "ticker": ticker,
            "date": _iso_day(holding.get("acquired_date")) or fallback_date,
            "units": units,
            "reason": tx_routes.OPENING_BALANCE_REASON,
        }
        cost = _positive(holding.get("cost_basis_gbp"))
        if cost is not None:
            transfer["price_gbp"] = round(cost / units, 8)
        transfers.append(transfer)
    return transfers, skipped


def _opening_cash(holding: Mapping[str, Any], day: str) -> dict[str, Any] | None:
    """A DEPOSIT (WITHDRAWAL if overdrawn) that reproduces the holding's cash balance, or None if zero."""
    balance = _number(holding.get("units"))
    if balance is None:
        balance = _number(holding.get("value_gbp"))
    balance = balance or 0.0
    amount_minor = round(abs(balance) * 100)
    if not amount_minor:
        return None
    return {
        "type": "DEPOSIT" if balance > 0 else "WITHDRAWAL",
        "ticker": CASH_TICKER,
        "date": day,
        "amount_minor": amount_minor,
        "currency": "GBP",
        "reason": tx_routes.OPENING_BALANCE_REASON,
    }


def plan_account(store: AccountsStore, owner: str, holdings_file: str, *, include_cash: bool = False) -> AccountPlan:
    account = holdings_file.removesuffix(".json")
    plan = AccountPlan(owner, account)
    holdings_doc = store.read_document(owner, holdings_file) or {}
    holdings = [h for h in holdings_doc.get("holdings") or [] if isinstance(h, Mapping)]
    if not holdings:
        return plan
    if account != account.lower():
        plan.skipped.append((holdings_file, "holdings file name is not lower-case; rename it first"))
        return plan
    tx_account = tx_routes._transactions_account_name(owner, account, store)
    tx_doc = store.read_document(owner, f"{tx_account}_transactions.json") or {}
    transactions = [t for t in tx_doc.get("transactions") or [] if isinstance(t, Mapping)]
    plan.transfers, plan.skipped = opening_transfers(
        transactions, holdings, include_cash=include_cash, trade_cash=tx_doc.get(TRADE_CASH_FLAG) is True
    )
    return plan


def apply_plan(store: AccountsStore, plan: AccountPlan) -> None:
    """Append the plan's transfers to the account's transactions file and rebuild it."""
    if not plan.transfers:
        return
    tx_account = tx_routes._transactions_account_name(plan.owner, plan.account, store)
    with tx_routes._locked_transactions_data(plan.owner, tx_account, store) as (data, _):
        data["transactions"].extend(plan.transfers)
    store.rebuild_portfolio(plan.owner, tx_account)


def plan_store(store: AccountsStore, owners: Sequence[str], *, include_cash: bool = False) -> list[AccountPlan]:
    plans = []
    for owner in owners:
        for name in store.list_owner_files(owner):
            if name.endswith(".json") and not tx_routes._is_non_holdings_file(name):
                plans.append(plan_account(store, owner, name, include_cash=include_cash))
    return plans


def _describe(transfer: Mapping[str, Any]) -> str:
    if transfer["ticker"] == CASH_TICKER:
        return f"{CASH_TICKER}: {transfer['type']} GBP {transfer['amount_minor'] / 100:,.2f}, dated {transfer['date']}"
    price = transfer.get("price_gbp")
    cost = f"at GBP {price:g}" if price is not None else "cost unknown"
    return f"{transfer['ticker']}: TRANSFER_IN {transfer['units']:g} units {cost}, dated {transfer['date']}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record holdings no transaction mentions as opening-balance transactions (dry run by default)."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--accounts-root", type=Path, help="Local accounts root (default: config accounts_root)")
    target.add_argument("--bucket", help="S3 bucket holding the writable accounts store")
    parser.add_argument("--owner", action="append", default=[], help="Only this owner (repeatable)")
    parser.add_argument("--write", action="store_true", help="Append the transfers and rebuild the accounts")
    parser.add_argument(
        "--include-cash", action="store_true", help="Also record an opening DEPOSIT for untracked CASH.GBP balances"
    )
    parser.add_argument(
        "--all", action="store_true", help="Required alongside --write with no --owner, to confirm every owner"
    )
    args = parser.parse_args(argv)
    if args.write and not args.owner and not args.all:
        parser.error("--write with no --owner also requires --all (writes every owner's accounts)")

    if args.bucket:
        store: AccountsStore = S3AccountsStore(bucket=args.bucket)
    else:
        root = args.accounts_root or (Path(config.accounts_root) if config.accounts_root else None)
        if root is None or not root.exists():
            parser.error("no accounts root: pass --accounts-root or --bucket")
        store = LocalAccountsStore(root=root)

    plans = plan_store(store, args.owner or store.list_owners(), include_cash=args.include_cash)
    converted = 0
    for plan in plans:
        if not plan.transfers and not plan.skipped:
            continue
        print(f"{plan.owner}/{plan.account}:")
        for transfer in plan.transfers:
            print(f"  {'recorded' if args.write else 'would record'} {_describe(transfer)}")
        for what, why in plan.skipped:
            print(f"  skipped {what}: {why}")
        if args.write:
            apply_plan(store, plan)
        converted += len(plan.transfers)
    verb = "Recorded" if args.write else "Would record"
    print(f"{verb} {converted} opening-balance transfer(s).{'' if args.write else ' Re-run with --write to apply.'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
