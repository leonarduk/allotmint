"""Canonical sector and region labels shared by every portfolio view.

Providers and holding sources spell the same sector or region in different
ways (Yahoo's "Financial Services" vs GICS "Financials", "UK" vs "United
Kingdom"). Grouping on the raw strings splits one exposure across several
buckets, so every place that hands a sector/region to a caller normalises it
here first (#8530).

The alias tables are exact-match (case-insensitive, whitespace-trimmed) on
purpose: a prefix or substring match would fold distinct sectors such as
"Real Estate Services" into "Real Estate" (#8292).
"""

from __future__ import annotations

from typing import Dict

# Sector label used for cash holdings in every sector view, instead of
# leaving the sector blank (shown as "Unknown sector" / "Other"). It must never
# be a key in SECTOR_ALIASES, or normalisation would relabel cash; a test guards
# this.
CASH_SECTOR_LABEL = "Cash"


def is_cash_instrument(ticker: object, instrument_type: object = None) -> bool:
    """True for ``CASH.<ccy>`` / legacy ``<ccy>.CASH`` / bare ``CASH`` tickers or ``instrument_type`` cash."""

    if isinstance(instrument_type, str) and instrument_type.strip().lower() == "cash":
        return True
    if not isinstance(ticker, str):
        return False
    symbol = ticker.strip().upper()
    return symbol == "CASH" or symbol.startswith("CASH.") or symbol.endswith(".CASH")


# Known aliases for the same region under different provider/holding-source
# labels. Deliberately narrow: only collapses labels that unambiguously refer
# to the same country (e.g. "UK" and "United Kingdom"), never broader
# groupings like "England" -> "Europe". See allotmint#7107.
REGION_ALIASES: Dict[str, str] = {
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "GB": "United Kingdom",
    "GBR": "United Kingdom",
    "GREAT BRITAIN": "United Kingdom",
}

# Known aliases for the same sector under different provider/holding-source
# labels, mapped to the GICS sector name. Deliberately narrow: only collapses
# labels that unambiguously refer to the same sector, never broader groupings
# like "Real Estate Services". See allotmint#7161, #8292 and #8530.
SECTOR_ALIASES: Dict[str, str] = {
    # REIT variants (#7161)
    "REAL ESTATE INVESTMENT TRUSTS": "Real Estate",
    "REAL ESTATE INVESTMENT TRUST": "Real Estate",
    "REITS": "Real Estate",
    "REIT": "Real Estate",
    # Yahoo Finance sector names -> GICS (#8530)
    "FINANCIAL SERVICES": "Financials",
    "TECHNOLOGY": "Information Technology",
    "CONSUMER DEFENSIVE": "Consumer Staples",
    "CONSUMER CYCLICAL": "Consumer Discretionary",
    "BASIC MATERIALS": "Materials",
    "HEALTHCARE": "Health Care",
    "COMMUNICATION": "Communication Services",
}


def normalise_sector_label(value: str) -> str:
    """Return the canonical sector for ``value``, or ``value`` trimmed if unknown."""

    key = value.strip()
    return SECTOR_ALIASES.get(key.upper(), key)


def normalise_region_label(value: str) -> str:
    """Return the canonical region for ``value``, or ``value`` trimmed if unknown."""

    key = value.strip()
    return REGION_ALIASES.get(key.upper(), key)


def normalise_optional_sector(value: object) -> str | None:
    """Like :func:`normalise_sector_label`, but pass blank/non-string values through as ``None``."""

    if not isinstance(value, str) or not value.strip():
        return None
    return normalise_sector_label(value)


def normalise_optional_region(value: object) -> str | None:
    """Like :func:`normalise_region_label`, but pass blank/non-string values through as ``None``."""

    if not isinstance(value, str) or not value.strip():
        return None
    return normalise_region_label(value)
