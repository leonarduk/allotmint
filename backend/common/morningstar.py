"""Resolve Morningstar security ids (SecIds) for instruments.

Morningstar quote pages are keyed by its own SecId (e.g. ``0P00014GY5``),
not the ISIN, and one ISIN has a SecId per listing (exchange + currency).
This looks the ISIN up in the public screener that Morningstar's own site
widgets use and picks the listing that matches the instrument's exchange
and currency. The endpoint is unofficial, so every failure resolves to
``None`` and callers fall back to a Morningstar search link.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

import requests

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SCREENER_URL = "https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener"
_TIMEOUT_SECONDS = 10

# AllotMint exchange suffix -> Morningstar exchange MICs it may list under.
EXCHANGE_MICS: dict[str, tuple[str, ...]] = {
    "L": ("XLON",),
    "N": ("XNYS", "XNAS", "ARCX", "BATS"),
    "DE": ("XETR", "XFRA"),
    "F": ("XFRA",),
    "TO": ("XTSE",),
    "MI": ("XMIL",),
    "AS": ("XAMS",),
    "PA": ("XPAR",),
    "SW": ("XSWX",),
}


def _row_mic(row: dict[str, Any]) -> str:
    """``EX$$$$XLON`` -> ``XLON``."""
    value = row.get("ExchangeId")
    return value.rstrip("$")[-4:].upper() if isinstance(value, str) else ""


def _row_currency(row: dict[str, Any]) -> str:
    value = row.get("Currency")
    return value.upper() if isinstance(value, str) else ""


def select_sec_id(rows: Iterable[dict[str, Any]], exchange: str, currency: Optional[str]) -> Optional[str]:
    """Pick the SecId for the listing on ``exchange``, preferring ``currency``.

    Pence-quoted London lines (GBX) list in GBP on Morningstar. Returns
    ``None`` when no row is on the exchange, rather than guessing a foreign
    listing whose quote page would show the wrong price.
    """
    mics = EXCHANGE_MICS.get(exchange.upper(), ())
    on_exchange = [r for r in rows if _row_mic(r) in mics and isinstance(r.get("SecId"), str)]
    if not on_exchange:
        return None
    wanted = (currency or "").upper()
    wanted = "GBP" if wanted == "GBX" else wanted
    for row in on_exchange:
        if wanted and _row_currency(row) == wanted:
            return row["SecId"]
    return on_exchange[0]["SecId"]


def _fetch_rows(isin: str) -> list[dict[str, Any]]:
    params = {
        "outputType": "json",
        "languageId": "en-GB",
        "securityDataPoints": "SecId|isin|ExchangeId|Currency",
        "term": isin,
    }
    response = requests.get(SCREENER_URL, params=params, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    rows = response.json().get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("isin") == isin]


def resolve_sec_id(isin: str, exchange: str, currency: Optional[str]) -> Optional[str]:
    """Return the Morningstar SecId for an ISIN's listing, or ``None``."""
    try:
        rows = _fetch_rows(isin)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Morningstar lookup failed for %s: %s", sanitise_log_value(isin), exc)
        return None
    return select_sec_id(rows, exchange, currency)
