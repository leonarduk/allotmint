"""Parser for Hargreaves Lansdown holdings exports."""

from __future__ import annotations

import csv
import io
from typing import List, LiteralString
import logging

from backend.routes.transactions import Transaction
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

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


def parse(data: bytes) -> List[Transaction]:
    """Parse a CSV export from Hargreaves Lansdown into holdings.

    The export contains columns such as ``Code``, ``Units held``,
    ``Price (pence)`` and ``Cost (£)``.  Prices in pence are converted to
    pounds and costs in pounds are scaled to ``amount_minor`` (pence).
    """
    logger.debug("Parsing Hargreaves Lansdown holdings")

    try:
        text = data.decode("utf-8", errors="ignore")
        text = skip_non_datatable_rows(text)

        reader = csv.DictReader(io.StringIO(text))

        holdings: List[Transaction] = []
        for row in reader:
            code = (row.get("Code") or row.get("code") or "").strip()
            units = _to_float(row.get("Units held") or row.get("Units"))
            price_pence = _to_float(row.get("Price (pence)") or row.get("Price"))
            price = price_pence / 100 if price_pence is not None else None
            cost = _to_float(row.get("Cost (£)") or row.get("Cost"))
            amount_minor = cost * 100 if cost is not None else None
            holdings.append(
                # TODO we maybe need a position object not Transaction
                Transaction(
                    owner="",
                    account="",
                    ticker=code or None,
                    price=price,
                    units=units,
                    amount_minor=amount_minor,
                )
            )
        return holdings
    except csv.Error as e:
        logger.error("Failed to parse Hargreaves Lansdown holdings: %s",
                     sanitise_log_value(e))
        raise e


def skip_non_datatable_rows(text: str) -> LiteralString:
    """
    Hargreaves Lansdown files have a pre-amble and footer we want to ignore.
    """
    lines = text.split("\n")

    logger.debug("Parsing %d rows", len(lines))

    ignore = True
    data = []
    for line in lines:
        if not line or "Totals" in line:
            ignore = True
        if line.startswith("Code"):
            ignore = False
        if not ignore:
            data.append(line)
    logger.debug("Returning %d rows", len(data))
    text = "\n".join(data)
    return text
