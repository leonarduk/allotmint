"""Declared dividend currency for instruments that pay in another currency (#10742).

Stored dividends are added to the closes as they are: ``corporate_actions``
assumes Yahoo reports them in the units it quotes ``Close`` in. That fails for
a company that declares its dividend in another currency than its listing
trades in. ``BCG.L`` (Baltic Classifieds) trades in sterling but declares
dividends in euro cents, and Yahoo stores them as EUR amounts, so total return
reinvested each one ~15% too large. Yahoo's ``Currency`` tag cannot decide
this on its own: it labels BCG.L ``EUR`` even for rows when the closes were
LSE pence.

An instrument's metadata (``instruments/<EX>/<SYM>.json``) may therefore carry
an optional top-level ``dividend_currency`` block::

    "dividend_currency": {
      "currency": "EUR",
      "rationale": "Dividends declared in euro cents; the LSE line trades in GBP",
      "reviewed": "2026-10-11"
    }

``currency``
    ISO code the stored dividend amounts are in (not a pence code).
``rationale``/``reviewed``
    Required non-empty text and ISO date, as for ``price_adjustments``.

:func:`convert_dividends` turns each stored amount into the instrument's own
price currency (``currency`` in the same metadata; ``GBX`` means pence) at the
rate in force on its ex-date, from the stored FX history
(``cache.load_fx_history``, ``Rate`` = GBP per unit) with the historical-price
gap-fill rule (``cache.align_fx_rates``). A dividend with no rate is not
guessed: the whole series is refused (``None``) and the caller falls back to
price return. An instrument without the block, or with an invalid one
(logged), is unchanged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

import numpy as np
import pandas as pd

from backend.common.instruments import get_instrument_meta
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DIVIDEND_CURRENCY_KEY = "dividend_currency"
_ISO_RE = re.compile(r"^[A-Z]{3}$")
_PENCE_CODES = frozenset({"GBX"})
_GBP = "GBP"


@dataclass(frozen=True)
class DividendCurrency:
    """A parsed ``dividend_currency`` block."""

    currency: str
    rationale: str
    reviewed: date


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _iso_currency(value: Any) -> str | None:
    """``value`` as an upper-case ISO code when it is one (pence codes excluded)."""
    if not isinstance(value, str) or not _ISO_RE.match(value.strip()):
        return None
    code = value.strip()
    return None if code in _PENCE_CODES else code


def validate_dividend_currency(meta: Mapping[str, Any] | None) -> list[str]:
    """Problems with ``meta["dividend_currency"]``, one message each; ``[]`` when valid or absent."""
    raw = (meta or {}).get(DIVIDEND_CURRENCY_KEY)
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return [f"{DIVIDEND_CURRENCY_KEY} must be a JSON object"]
    problems: list[str] = []
    if _iso_currency(raw.get("currency")) is None:
        problems.append(
            f"{DIVIDEND_CURRENCY_KEY}: currency {raw.get('currency')!r} is not an ISO code (pence is not supported)"
        )
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        problems.append(f"{DIVIDEND_CURRENCY_KEY}: rationale is required")
    if _iso_date(raw.get("reviewed")) is None:
        problems.append(f"{DIVIDEND_CURRENCY_KEY}: reviewed {raw.get('reviewed')!r} is not an ISO date")
    return problems


def parse_dividend_currency(meta: Mapping[str, Any] | None) -> DividendCurrency | None:
    """The typed block, or ``None`` when absent. Raises ``ValueError`` when invalid."""
    problems = validate_dividend_currency(meta)
    if problems:
        raise ValueError("; ".join(problems))
    raw = (meta or {}).get(DIVIDEND_CURRENCY_KEY)
    if raw is None:
        return None
    return DividendCurrency(
        currency=raw["currency"].strip(),
        rationale=raw["rationale"].strip(),
        reviewed=date.fromisoformat(raw["reviewed"].strip()),
    )


def _fx(currency: str) -> pd.DataFrame:
    """Stored ``currency``->GBP rates; never fetches."""
    # Imported here: ``cache`` pulls in the fetch stack, which this module must not load eagerly.
    from backend.timeseries.cache import load_fx_history

    return load_fx_history(currency)


def _gbp_per_unit(currency: str, dates: pd.Index) -> pd.Series:
    """GBP per unit of ``currency`` on each of ``dates`` (NaN where no rate is in force)."""
    if currency == _GBP:
        return pd.Series(1.0, index=dates)
    from backend.timeseries.cache import align_fx_rates

    return align_fx_rates(_fx(currency), dates)


def convert_dividends(dividends: pd.Series, ticker: str, exchange: str) -> pd.Series | None:
    """``dividends`` in the instrument's price currency, or ``None`` when a rate is missing.

    Returns ``dividends`` itself when the instrument declares no (valid)
    ``dividend_currency``, or the declared currency is the price currency.
    ``attrs`` are carried over; the input is never mutated.
    """
    if dividends is None or dividends.empty:
        return dividends
    full = f"{ticker}.{exchange}".upper() if exchange else str(ticker).upper()
    meta = get_instrument_meta(full)
    if not meta or DIVIDEND_CURRENCY_KEY not in meta:
        return dividends
    try:
        declared = parse_dividend_currency(meta)
    except ValueError as exc:
        logger.warning(
            "Ignoring invalid dividend_currency for %s: %s", sanitise_log_value(full), sanitise_log_value(exc)
        )
        return dividends
    price_code = str(meta.get("currency") or "").strip().upper()
    pence = price_code in _PENCE_CODES
    price_currency = _GBP if pence else _iso_currency(price_code)
    if declared is None or declared.currency == price_code:
        return dividends
    if price_currency is None:
        # The dividends are declared foreign, so passing them through would
        # reinvest them unconverted; refuse rather than guess the price currency.
        logger.warning(
            "Cannot convert %s dividends of %s: instrument currency %s is not supported",
            sanitise_log_value(declared.currency),
            sanitise_log_value(full),
            sanitise_log_value(price_code or None),
        )
        return None
    dates = dividends.index
    ratio = _gbp_per_unit(declared.currency, dates) / _gbp_per_unit(price_currency, dates)
    if ratio.isna().any():
        logger.warning(
            "No %s->%s rate for %s dividend(s) of %s; not converting",
            sanitise_log_value(declared.currency),
            sanitise_log_value(price_currency),
            sanitise_log_value(int(ratio.isna().sum())),
            sanitise_log_value(full),
        )
        return None
    scale = 100.0 if pence else 1.0
    out = pd.to_numeric(dividends, errors="coerce") * ratio.to_numpy(dtype=float) * np.float64(scale)
    out.attrs = dict(dividends.attrs)
    return out
