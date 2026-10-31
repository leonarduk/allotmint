"""Bulk CSV import of purchase prices for holdings already on file (#10095).

A user whose holdings arrived as a snapshot (a holdings CSV, or typed in
before ``/input`` recorded transactions) has units but no cost basis. This
module turns a CSV of purchase lots -- ``ticker, date, units, unit_cost`` and
optionally ``owner``/``account`` -- into priced ``TRANSFER_IN`` rows that the
holdings rebuild (:mod:`backend.common.holdings_rebuild`) books as the
holding's Section 104 cost.

Two rules keep the import from changing what is held:

* Only a holding that no transaction mentions yet is filled. A holding the
  ledger already tracks gets its cost from those transactions; adding lots
  on top would double its units.
* A holding's lots must add up to the units it holds now. The lots then
  *replace* the snapshot units one for one, so units are unchanged and the
  whole holding has a recorded cost (never a partial one).

Prices are GBP per unit. A pence price entered as pounds is not blocked
here: the booked-cost plausibility band in ``holding_utils`` flags the
resulting cost as ``book_suspect``, which keeps the holding on the
cost-basis checklist.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.common.holdings_rebuild import name_aliases, tracked_instruments
from backend.common.ticker_utils import canonical_ticker

COST_BASIS_IMPORT_REASON = "Purchase price from cost-basis CSV import"
REQUIRED_COLUMNS = ("ticker", "date", "units", "unit_cost")
# Lot units may differ from the units held by this much (float noise from a
# spreadsheet) and still count as covering the whole holding.
UNITS_TOLERANCE = 1e-6

# Accepted header spellings, after lower-casing and turning spaces/dashes
# into underscores.
_COLUMN_ALIASES = {
    "ticker": "ticker",
    "symbol": "ticker",
    "code": "ticker",
    "date": "date",
    "purchase_date": "date",
    "trade_date": "date",
    "units": "units",
    "quantity": "units",
    "unit_cost": "unit_cost",
    "unit_cost_gbp": "unit_cost",
    "unit_price": "unit_cost",
    "price": "unit_cost",
    "price_gbp": "unit_cost",
    "cost_per_unit": "unit_cost",
    "owner": "owner",
    "account": "account",
}
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")
_NUMBER_JUNK = re.compile(r"[£,\s]")


class CostBasisCsvError(ValueError):
    """The file as a whole cannot be read as a purchase-price CSV."""


@dataclass(frozen=True)
class PurchaseLot:
    """One parsed CSV row: ``units`` bought on ``date`` at ``unit_cost`` GBP each."""

    line: int
    ticker: str
    date: str
    units: float
    unit_cost: float
    owner: Optional[str] = None
    account: Optional[str] = None


def _normalise_header(name: str) -> str:
    key = re.sub(r"[\s\-]+", "_", (name or "").strip().lower())
    return _COLUMN_ALIASES.get(key, key)


def _positive_number(raw: str, field: str) -> float:
    text = _NUMBER_JUNK.sub("", raw or "")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{field} {raw!r} is not a number") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be greater than 0")
    return value


def _iso_date(raw: str, latest: date) -> str:
    text = (raw or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if parsed > latest:
            raise ValueError("date cannot be in the future")
        return parsed.isoformat()
    raise ValueError(f"date {raw!r} is not YYYY-MM-DD or DD/MM/YYYY")


def _optional(row: Mapping[str, Any], field: str) -> Optional[str]:
    value = str(row.get(field) or "").strip()
    return value or None


def _lot_from_row(line: int, row: Mapping[str, Any], latest: date) -> PurchaseLot:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    return PurchaseLot(
        line=line,
        ticker=ticker,
        date=_iso_date(str(row.get("date") or ""), latest),
        units=_positive_number(str(row.get("units") or ""), "units"),
        unit_cost=_positive_number(str(row.get("unit_cost") or ""), "unit_cost"),
        owner=_optional(row, "owner"),
        account=_optional(row, "account"),
    )


def _csv_reader(data: bytes) -> csv.DictReader:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CostBasisCsvError("File is not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    headers = [_normalise_header(h) for h in reader.fieldnames or []]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise CostBasisCsvError(f"Missing column(s): {', '.join(missing)}")
    reader.fieldnames = headers
    return reader


def parse_purchase_lots(data: bytes, latest: Optional[date] = None) -> Tuple[List[PurchaseLot], List[Dict[str, Any]]]:
    """Parse ``data`` into lots, plus a ``skipped`` entry for each unusable row.

    ``latest`` is the last acceptable purchase date (default tomorrow, the
    same day of timezone slack the transaction routes allow). Blank lines
    are ignored. Raises :class:`CostBasisCsvError` when the file is not text
    or lacks a required column.
    """
    latest = latest or date.today() + timedelta(days=1)
    lots: List[PurchaseLot] = []
    skipped: List[Dict[str, Any]] = []
    # Line 1 is the header, so the first data row is line 2.
    for line, row in enumerate(_csv_reader(data), start=2):
        if not any(str(v or "").strip() for v in row.values()):
            continue
        try:
            lots.append(_lot_from_row(line, row, latest))
        except ValueError as exc:
            skipped.append({"line": line, "ticker": _optional(row, "ticker"), "skip_reason": str(exc)})
    return lots, skipped


def _find_holding(holdings: Sequence[Mapping[str, Any]], key: str) -> Optional[Mapping[str, Any]]:
    for holding in holdings:
        if canonical_ticker(str(holding.get("ticker") or "")) == key:
            return holding
    return None


def _held_units(holding: Mapping[str, Any]) -> float:
    try:
        units = float(holding.get("units") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return units if math.isfinite(units) else 0.0


def _lot_transactions(ticker: str, lots: Sequence[PurchaseLot], held: float) -> List[Dict[str, Any]]:
    """Priced TRANSFER_INs for ``lots``, the last absorbing float noise so they sum to ``held`` exactly."""
    txs = [
        {
            "type": "TRANSFER_IN",
            "ticker": ticker,
            "date": lot.date,
            "units": lot.units,
            "price_gbp": lot.unit_cost,
            "reason": COST_BASIS_IMPORT_REASON,
        }
        for lot in lots
    ]
    txs[-1]["units"] = round(held - sum(lot.units for lot in lots[:-1]), 8)
    return txs


def plan_cost_basis_lots(
    transactions: Sequence[Mapping[str, Any]],
    holdings: Sequence[Mapping[str, Any]],
    ticker: str,
    lots: Sequence[PurchaseLot],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """``(transactions to append, None)`` that give ``ticker``'s holding a cost, or ``([], skip reason)``.

    ``lots`` are all of the CSV's lots for this holding. See the module
    docstring for why a tracked holding, or lots that do not add up to the
    units held, is skipped rather than imported.
    """
    key = canonical_ticker(ticker)
    holding = _find_holding(holdings, key)
    if holding is None:
        return [], f"no {ticker} holding in this account"
    if key in tracked_instruments(transactions, name_aliases(transactions, holdings)):
        return [], f"{ticker} already has transactions, which set its cost; edit those in the transaction log instead"
    held = _held_units(holding)
    total = sum(lot.units for lot in lots)
    if abs(total - held) > UNITS_TOLERANCE:
        return [], f"lot units add up to {total:g}, but {held:g} units are held"
    if held - sum(lot.units for lot in lots[:-1]) <= 0:
        # The last lot absorbs float noise; it must not end up zero or negative.
        return [], f"lot units add up to {total:g}, but the last lot would leave no units for {held:g} held"
    return _lot_transactions(str(holding.get("ticker")), lots, held), None
