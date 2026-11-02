"""Keep estimated per-ticker dividends from double counting booked income (#11086).

Two writers can record the same dividend cash:

* the dividend refresh bot (:func:`backend.common.dividends.refresh_dividends`)
  writes one estimated ``DIVIDEND`` row per ticker and ex-date
  (per-share amount x units held), and
* a broker's booked income -- e.g. Hargreaves Lansdown's monthly
  "Transfer from Income Account" -- recorded as a ticker-less ``DIVIDEND`` row
  holding the cash actually received.

The booked row is the income. An estimated row dated on or before the
account's latest booked row is covered by it, so it is flagged
``attribution_only``: it still says which holding paid (the Dividends page's
per-holding breakdown) but every income, cash and return calculation skips it.
An estimated row after the latest booked row stays income until the next
booked row arrives, so recent dividends are not missing in the meantime.

A booked ticker-less row can also be attributed by hand (#10060): the owner
splits it into per-ticker rows, read from their broker's income statement,
with :func:`attribute_booked_dividend`. The parts add up to the original
amount (any unattributed remainder stays a ticker-less row), so income totals
and cash are unchanged. Each part is flagged ``attributed_sweep``: it is still
booked income from the sweep, so it keeps counting towards the cutoff above
and the estimates it covers stay ``attribution_only``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

ATTRIBUTION_ONLY_KEY = "attribution_only"
ESTIMATED_KEY = "estimated"
#: A per-ticker part of a booked income sweep, attributed by the owner (#10060).
ATTRIBUTED_SWEEP_KEY = "attributed_sweep"
# A part does not carry the sweep's trade-shaped fields, if it had any.
_DROPPED_ON_PARTS = ("units", "shares", "price", "price_gbp")
# Rows written before refresh_dividends set ESTIMATED_KEY carry only this reason.
ESTIMATED_DIVIDEND_REASON = "Automated dividend import"
_DIVIDEND_TYPES = {"DIVIDEND", "DIVIDENDS"}
# Dates compare as text, so only strict YYYY-MM-DD values take part.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_attribution_only(tx: Mapping[str, Any]) -> bool:
    """Whether ``tx`` is an estimate covered by booked income (never counted as income)."""
    return tx.get(ATTRIBUTION_ONLY_KEY) is True


def is_estimated_dividend(tx: Mapping[str, Any]) -> bool:
    """Whether ``tx`` is a dividend refresh estimate rather than booked cash."""
    if str(tx.get("type") or "").upper() not in _DIVIDEND_TYPES:
        return False
    return tx.get(ESTIMATED_KEY) is True or tx.get("reason") == ESTIMATED_DIVIDEND_REASON


class AttributionError(ValueError):
    """A dividend row cannot be attributed as asked."""


def _is_unattributed_sweep(tx: Mapping[str, Any]) -> bool:
    return (
        str(tx.get("type") or "").upper() in _DIVIDEND_TYPES
        and not str(tx.get("ticker") or "").strip()
        and not is_estimated_dividend(tx)
    )


def _is_booked_income_sweep(tx: Mapping[str, Any]) -> bool:
    """A booked income row: a ticker-less sweep, or a part of one attributed by hand."""
    if _is_unattributed_sweep(tx):
        return True
    return tx.get(ATTRIBUTED_SWEEP_KEY) is True and not is_estimated_dividend(tx)


def booked_income_cutoff(transactions: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """ISO date of the account's latest ticker-less booked dividend row, if any."""
    dates = [str(tx.get("date") or "")[:10] for tx in transactions if _is_booked_income_sweep(tx)]
    dated = [d for d in dates if _ISO_DATE_RE.match(d)]
    return max(dated) if dated else None


def mark_attribution_only(transactions: List[MutableMapping[str, Any]]) -> int:
    """Flag the account's estimated dividends covered by booked income; return rows changed.

    ``transactions`` must be one account's rows: the cutoff is per account.
    Re-running is a no-op, and a row the cutoff no longer covers is unflagged.
    """
    cutoff = booked_income_cutoff(transactions)
    changed = 0
    for tx in transactions:
        if not is_estimated_dividend(tx):
            continue
        day = str(tx.get("date") or "")[:10]
        covered = bool(cutoff and _ISO_DATE_RE.match(day) and day <= cutoff)
        if covered and not is_attribution_only(tx):
            tx[ATTRIBUTION_ONLY_KEY] = True
            changed += 1
        elif not covered and ATTRIBUTION_ONLY_KEY in tx:
            del tx[ATTRIBUTION_ONLY_KEY]
            changed += 1
    return changed


def _sweep_amount(entry: Mapping[str, Any]) -> float:
    if not _is_unattributed_sweep(entry):
        raise AttributionError("Only a booked dividend with no ticker can be attributed to holdings")
    amount = entry.get("amount_minor")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not amount > 0:
        raise AttributionError("The dividend has no positive amount to attribute")
    return float(amount)


def _check_parts(parts: Sequence[Tuple[str, int]], total: float) -> None:
    tickers = [ticker for ticker, _ in parts]
    if not parts or any(not ticker for ticker in tickers):
        raise AttributionError("Name a ticker for every part")
    if len(set(tickers)) != len(tickers):
        raise AttributionError("Each ticker can appear only once")
    if any(amount <= 0 for _, amount in parts):
        raise AttributionError("Every part needs a positive amount")
    if sum(amount for _, amount in parts) > round(total, 2):
        raise AttributionError("The parts add up to more than the dividend")


def attribute_booked_dividend(entry: Mapping[str, Any], parts: Sequence[Tuple[str, int]]) -> List[Dict[str, Any]]:
    """The rows that replace a booked ticker-less dividend ``entry`` split into ``parts``.

    ``parts`` is ``[(ticker, amount_minor), ...]``. One row per part, flagged
    ``attributed_sweep``, then a ticker-less row for any remainder, so the
    rows always add up to the original ``amount_minor``. The source's
    ``external_id`` stays on the remainder row (else the first part) so
    re-importing the source cannot add the sweep back; the other parts get a
    derived id. Raises :class:`AttributionError` when ``entry`` is not a
    booked ticker-less dividend or ``parts`` do not fit inside it.
    """
    total = _sweep_amount(entry)
    _check_parts(parts, total)
    rows: List[Dict[str, Any]] = []
    for ticker, amount in parts:
        row = {key: value for key, value in entry.items() if key not in _DROPPED_ON_PARTS}
        row.update({"ticker": ticker, "amount_minor": amount, ATTRIBUTED_SWEEP_KEY: True})
        rows.append(row)
    remainder = round(total - sum(amount for _, amount in parts), 2)
    if remainder > 0:
        rows.append({**entry, "amount_minor": remainder})
    source_id = entry.get("external_id")
    if source_id:
        keeper = rows[-1] if remainder > 0 else rows[0]
        for row in rows:
            row["external_id"] = source_id if row is keeper else f"{source_id}#attr-{row['ticker']}"
    return rows
