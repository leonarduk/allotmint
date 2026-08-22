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


def parse(data: bytes) -> List[Transaction]:
    """Parse a CSV export from Hargreaves Lansdown into holdings.

    The export contains columns such as ``Code``, ``Units held``,
    ``Price (pence)`` and ``Cost (£)``.  Prices in pence are converted to
    pounds and costs in pounds are scaled to ``amount_minor`` (pence).
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
            code = (row.get("Code") or row.get("code") or "").strip()
            units = _to_float(row.get("Units held") or row.get("Units"))
            price = _price_in_gbp(row, units)
            cost = _to_float(row.get("Cost (£)") or row.get("Cost"))
            amount_minor = cost * 100 if cost is not None else None
            holdings.append(add_position(ticker=code, price=price, units=units, amount_minor=amount_minor))
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
