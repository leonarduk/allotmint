"""Parser for Hargreaves Lansdown holdings exports."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, List

from backend.logging_setup import sanitise_log_value
from backend.routes.transactions import Transaction

logger = logging.getLogger(__name__)

_PENCE_PRICE_COLUMNS = ("Price (pence)", "Price (GBX)")
_POUND_PRICE_COLUMNS = ("Price (£)", "Price (GBP)")
_NAME_COLUMNS = ("Stock", "Security", "Name", "Description")

# HL appends ``*R`` to the stock name of transferred-in / re-registered lines,
# e.g. "United Parcel Service Class 'B' Com Stock US$0.01 (CDI) *R" (#8474).
# Tolerate it as a leading or trailing token on either the name or the code.
_TRANSFER_MARKER_RE = re.compile(r"^\s*\*R\b\s*|\s*\*R\s*$", re.IGNORECASE)
TRANSFER_IN_TYPE = "TRANSFER_IN"
MISSING_COST_COMMENT = "Transferred in (*R); cost basis missing from HL export"


def _to_float(value: str | None) -> float | None:
    """Convert a string to float, ignoring commas and blanks."""
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _first_number(row: dict[str, str | None], columns: tuple[str, ...]) -> float | None:
    """Return the first numeric value found under ``columns``.

    A column that exists but is blank/``None`` is skipped rather than
    short-circuiting the scan, so a later column can still supply a valid
    value.
    """
    for column in columns:
        if column in row:
            value = _to_float(row[column])
            if value is not None:
                return value
    return None


def _price_in_gbp(row: dict[str, str | None], units: float | None) -> float | None:
    """Read a price and verify its GBP/GBX scale against market value.

    HL exports label prices in either pounds or pence.  The market-value
    column provides an independent check: if the labelled interpretation is
    about 100 times away but the alternative agrees, use the alternative.
    This protects imports when an export uses a stale or ambiguous heading.
    """
    raw_pence = _first_number(row, _PENCE_PRICE_COLUMNS)
    raw_pounds = _first_number(row, _POUND_PRICE_COLUMNS)
    raw_price = raw_pence if raw_pence is not None else raw_pounds
    if raw_price is None:
        raw_price = _to_float(row.get("Price"))
        labelled_price = raw_price / 100 if raw_price is not None else None
    else:
        labelled_price = raw_price / 100 if raw_pence is not None else raw_price

    value_gbp = _first_number(row, ("Value (£)", "Value (GBP)", "Value"))
    if (
        raw_price is None
        or labelled_price is None
        or units is None
        or units <= 0
        or value_gbp is None
        or value_gbp <= 0
    ):
        return labelled_price

    alternative_price = raw_price if labelled_price != raw_price else raw_price / 100
    labelled_error = abs((units * labelled_price) - value_gbp) / value_gbp
    alternative_error = abs((units * alternative_price) - value_gbp) / value_gbp
    if labelled_error > 0.5 and alternative_error < 0.1:
        return alternative_price
    return labelled_price


def _strip_transfer_marker(value: str) -> tuple[str, bool]:
    """Return ``value`` without an HL ``*R`` marker and whether one was present."""
    stripped = _TRANSFER_MARKER_RE.sub("", value).strip()
    return stripped, stripped != value.strip()


def _first_text(row: dict[str, str | None], columns: tuple[str, ...]) -> str:
    """Return the first non-blank text value found under ``columns``."""
    for column in columns:
        value = (row.get(column) or "").strip()
        if value:
            return value
    return ""


def _parse_row(row: dict[str, str | None]) -> Transaction:
    """Convert one HL holdings row into a position record.

    Rows marked ``*R`` (transferred in) with a booked cost are typed
    ``TRANSFER_IN`` so the transaction replay
    (``backend.common.holdings_rebuild``) can pick up that cost.  A
    missing/zero cost on such a row is left missing (never guessed) and
    flagged -- see :func:`_mark_transfer_in`.
    """
    code, code_marked = _strip_transfer_marker((row.get("Code") or row.get("code") or "").strip())
    name, name_marked = _strip_transfer_marker(_first_text(row, _NAME_COLUMNS))
    units = _to_float(row.get("Units held") or row.get("Units"))
    price = _price_in_gbp(row, units)
    cost = _to_float(row.get("Cost (£)") or row.get("Cost"))
    amount_minor = cost * 100 if cost is not None else None
    position = add_position(ticker=code, price=price, units=units, amount_minor=amount_minor)
    position.instrument_name = name or None
    if code_marked or name_marked:
        _mark_transfer_in(position)
    return position


def _mark_transfer_in(position: Transaction) -> None:
    """Type ``position`` as a transfer-in, or flag it when its cost is unknown.

    Only a row with a booked cost is typed ``TRANSFER_IN``.  Without one the
    replay would fall back to ``price x units`` -- and ``price`` here is the
    *current* market price, not an acquisition price -- which would write a
    guessed cost into the ledger.  So a cost-less row stays untyped (ignored
    by the replay, as before) with ``amount_minor`` left missing, a
    ``comments`` flag, and a warning asking for a cost-basis import.
    """
    if position.amount_minor:
        position.type = TRANSFER_IN_TYPE
        return
    position.amount_minor = None
    position.comments = MISSING_COST_COMMENT
    logger.warning(
        "Hargreaves transferred-in holding %s has no booked cost; cost basis needs importing",
        sanitise_log_value(position.ticker or position.instrument_name),
    )


def parse(data: bytes) -> List[Transaction]:
    """Parse a CSV export from Hargreaves Lansdown into holdings.

    The export contains columns such as ``Code``, ``Stock``, ``Units held``,
    ``Price (pence)`` and ``Cost (£)``.  Prices in pence are converted to
    pounds and costs in pounds are scaled to ``amount_minor`` (pence).  The
    stock name is kept as ``instrument_name``; ``*R`` (transferred-in) rows are
    handled by :func:`_parse_row`.
    """
    logger.debug("Parsing Hargreaves Lansdown holdings")

    try:
        text = data.decode("utf-8", errors="replace")
        text, cash = skip_non_datatable_rows(text)

        holdings: List[Transaction] = []

        if cash:
            holdings.append(add_position(ticker="CASH.GBP", price=1.0, units=cash, amount_minor=cash))
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            holdings.append(_parse_row(row))
        return holdings
    except csv.Error as e:
        logger.error("Failed to parse Hargreaves Lansdown holdings: %s", sanitise_log_value(e))
        raise e


def add_position(
    amount_minor: float | None,
    ticker: str,
    price: float | None,
    units: float | None,
) -> Any:
    # TODO we maybe need a position object not Transaction
    return Transaction(
        owner="",
        account="",
        ticker=ticker or None,
        price=price,
        units=units,
        amount_minor=amount_minor,
    )


def skip_non_datatable_rows(text: str) -> tuple[str, float]:
    """
    Hargreaves Lansdown files have a pre-amble and footer we want to ignore.
    """
    lines = text.split("\n")

    logger.debug("Parsing %d rows", len(lines))

    ignore = True
    data = []
    cash = 0.0
    for line in lines:
        if "Total cash:" in line:
            total = _to_float(re.sub(r"[^\d.]", "", line.strip().replace("Total cash:", "")))
            if total:
                cash += total

        if not line:
            ignore = True
        if line.startswith("Code"):
            ignore = False
        if not ignore:
            data.append(line)

    if data:
        # Remove totals line if present at end
        if "Totals" in data[len(data) - 1]:
            data.pop(len(data) - 1)

    logger.debug("Returning %d rows", len(data))
    text = "\n".join(data)
    return text, cash
