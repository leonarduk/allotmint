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
    """``EX$$$$XLON`` -> ``XLON``; ``""`` for ``EX$$$$$$$$`` (no exchange) or junk."""
    value = row.get("ExchangeId")
    if not isinstance(value, str) or len(value) < 4:
        return ""
    mic = value[-4:].upper()
    return mic if mic.isalnum() else ""


def _sterling(currency: object) -> str:
    """Upper-case currency code with pence (GBX/GBp) folded into GBP."""
    code = currency.upper() if isinstance(currency, str) else ""
    return "GBP" if code == "GBX" else code


def _row_currency(row: dict[str, Any]) -> str:
    return _sterling(row.get("Currency"))


def select_sec_id(rows: Iterable[dict[str, Any]], exchange: str, currency: Optional[str]) -> Optional[str]:
    """Pick the SecId for the listing on ``exchange`` in ``currency``.

    Pence-quoted London lines (GBX) list in GBP on Morningstar. Never
    guesses: returns ``None`` when no listing on the exchange is in the
    currency (another line's quote page would show the wrong price), or,
    without a currency, when the exchange has more than one listing.
    """
    mics = EXCHANGE_MICS.get(exchange.upper(), ())
    on_exchange = [r for r in rows if _row_mic(r) in mics and isinstance(r.get("SecId"), str)]
    wanted = _sterling(currency)
    if not wanted:
        return on_exchange[0]["SecId"] if len(on_exchange) == 1 else None
    return next((r["SecId"] for r in on_exchange if _row_currency(r) == wanted), None)


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


# Listings already looked up with no match, so a research page viewed again
# does not re-query Morningstar for them until the process restarts. Bounded
# by clearing when full: the catalogue is a few hundred instruments, so the
# cap is only a backstop.
_UNRESOLVED: set[tuple[str, str, str]] = set()
_UNRESOLVED_MAX = 1024


def resolve_sec_id(isin: str, exchange: str, currency: Optional[str]) -> Optional[str]:
    """Return the Morningstar SecId for an ISIN's listing, or ``None``."""
    key = (isin, exchange.upper(), (currency or "").upper())
    if key in _UNRESOLVED:
        return None
    try:
        rows = _fetch_rows(isin)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Morningstar lookup failed for %s: %s", sanitise_log_value(isin), sanitise_log_value(exc))
        return None
    sec_id = select_sec_id(rows, exchange, currency)
    if sec_id is None:
        if len(_UNRESOLVED) >= _UNRESOLVED_MAX:
            _UNRESOLVED.clear()
        _UNRESOLVED.add(key)
    return sec_id
