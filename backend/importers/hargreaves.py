"""Parser for Hargreaves Lansdown holdings exports."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, List

from backend.common.ticker_utils import canonical_ticker
from backend.logging_setup import sanitise_log_value
from backend.routes.transactions import Transaction

logger = logging.getLogger(__name__)

_PENCE_PRICE_COLUMNS = ("Price (pence)", "Price (GBX)")
_POUND_PRICE_COLUMNS = ("Price (£)", "Price (GBP)")
_NAME_COLUMNS = ("Stock", "Security", "Name", "Description")

# HL appends ``*R`` to the stock name of transferred-in / re-registered lines,
# e.g. "United Parcel Service Class 'B' Com Stock US$0.01 (CDI) *R" (#8474).
# Tolerate it as a leading or trailing token on either the name or the code.
# A leading marker must be followed by a word boundary, so "*RADBE" is left alone.
# The trailing case deliberately has no boundary: HL tickers never contain "*",
# and HL sometimes glues the marker on ("FOO*R"), so that is stripped too.
_TRANSFER_MARKER_RE = re.compile(r"^\s*\*R\b\s*|\s*\*R\s*$", re.IGNORECASE)
TRANSFER_IN_COMMENT = "Transferred in (HL *R)"
MISSING_COST_COMMENT = "cost basis missing from HL export"
PRICE_FROM_VALUE_COMMENT = "price derived from Value (£) / units: labelled price disagreed"

# Relative gap between ``units * price`` and ``Value (£)`` beyond which the
# labelled price is not trusted (#9679).
_VALUE_TOLERANCE = 0.05


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
    """Read a price and verify it in GBP against market value; see :func:`_checked_price`."""
    price, _derived = _checked_price(row, units)
    return price


def _checked_price(row: dict[str, str | None], units: float | None) -> tuple[float | None, bool]:
    """Read a price, verify it against market value, and say whether it was derived.

    HL exports label prices in either pounds or pence.  The market-value
    column provides an independent check: if the labelled interpretation is
    about 100 times away but the alternative agrees, use the alternative.
    This protects imports when an export uses a stale or ambiguous heading.
    When neither reading is within ``_VALUE_TOLERANCE`` of ``Value (£)`` --
    e.g. a price quoted in USD (#9679) -- ``Value (£)`` is authoritative and
    the price is derived as ``value / units``; the second element is then
    ``True`` so the row can be flagged.
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
        return labelled_price, False

    alternative_price = raw_price if labelled_price != raw_price else raw_price / 100
    labelled_error = abs((units * labelled_price) - value_gbp) / value_gbp
    alternative_error = abs((units * alternative_price) - value_gbp) / value_gbp
    if labelled_error > 0.5 and alternative_error < 0.1:
        return alternative_price, False
    if labelled_error <= _VALUE_TOLERANCE:
        return labelled_price, False
    return value_gbp / units, True


def _strip_transfer_marker(value: str) -> tuple[str, bool]:
    """Return ``value`` without an HL ``*R`` marker and whether one was present."""
    marked = bool(_TRANSFER_MARKER_RE.search(value))
    return _TRANSFER_MARKER_RE.sub("", value).strip(), marked


def _first_text(row: dict[str, str | None], columns: tuple[str, ...]) -> str:
    """Return the first non-blank text value under ``columns``, matching headers case-insensitively."""
    by_lower = {str(key).strip().lower(): value for key, value in row.items() if key is not None}
    for column in columns:
        value = (by_lower.get(column.lower()) or "").strip()
        if value:
            return value
    return ""


def _parse_row(row: dict[str, str | None]) -> Transaction:
    """Convert one HL holdings row into a position record.

    Rows marked ``*R`` (transferred in) have the marker stripped and are
    flagged in ``comments`` -- see :func:`_mark_transfer_in`.  Like every other
    row they stay untyped.  The code is canonicalised, so HL's padded LSE
    EPICs (``BP.``, ``AV.``) are stored as ``BP.L``/``AV.L`` rather than with an
    empty exchange; a bare code stays bare.
    """
    code, code_marked = _strip_transfer_marker((row.get("Code") or row.get("code") or "").strip())
    code = canonical_ticker(code)
    name, name_marked = _strip_transfer_marker(_first_text(row, _NAME_COLUMNS))
    units = _to_float(row.get("Units held") or row.get("Units"))
    price, price_derived = _checked_price(row, units)
    cost = _to_float(row.get("Cost (£)") or row.get("Cost"))
    amount_minor = cost * 100 if cost is not None else None
    position = add_position(ticker=code, price=price, units=units, amount_minor=amount_minor)
    if name:
        position.instrument_name = name
    if price_derived:
        _append_comment(position, PRICE_FROM_VALUE_COMMENT)
        logger.warning(
            "Hargreaves price for %s disagrees with Value (£); using Value (£) / units",
            sanitise_log_value(code or name),
        )
    if code_marked or name_marked:
        _mark_transfer_in(position)
    return position


def _append_comment(position: Transaction, note: str) -> None:
    """Append ``note`` to ``position.comments`` rather than overwriting it."""
    position.comments = f"{position.comments}; {note}" if position.comments else note


def _mark_transfer_in(position: Transaction) -> None:
    """Record the HL ``*R`` transfer-in marker on ``position`` without typing it.

    The row is deliberately *not* typed ``TRANSFER_IN``.  A holdings export
    carries no dates, so an undated transfer-in would be replayed last by
    ``backend.common.holdings_rebuild`` and add its units on top of the dated
    BUYs the ledger already holds for the position -- double-counting it.  The
    marker is kept in ``comments`` instead.  A missing/zero cost is left
    missing (never guessed), flagged in ``comments`` and logged.
    """
    _append_comment(position, TRANSFER_IN_COMMENT)
    if position.amount_minor is not None and position.amount_minor != 0:
        return
    position.amount_minor = None
    _append_comment(position, MISSING_COST_COMMENT)
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
