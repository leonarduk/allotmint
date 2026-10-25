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
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping, MutableMapping, Optional, Sequence

ATTRIBUTION_ONLY_KEY = "attribution_only"
ESTIMATED_KEY = "estimated"
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


def _is_booked_income_sweep(tx: Mapping[str, Any]) -> bool:
    return (
        str(tx.get("type") or "").upper() in _DIVIDEND_TYPES
        and not str(tx.get("ticker") or "").strip()
        and not is_estimated_dividend(tx)
    )


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
