"""ISIN vs listing-exchange checks for instrument metadata writes (#9295).

An instrument file is keyed by an exchange-qualified ticker (``BMY.L``), but
a bare symbol is shared across markets: ``BMY`` is Bloomsbury Publishing in
London and Bristol-Myers Squibb in New York. Metadata resolved by the bare
symbol gives a London line the US company's ISIN (``US1101221083``), and the
sector/region that go with it. #9295 found eight such files.

An ISIN's first two letters are the issuer's country (or ``XS`` for
international securities), so a London line whose ISIN starts ``US`` or
``IL`` is suspect. It is not proof: an overseas company can trade in London
through depositary interests (BHP ``AU``, Hiscox ``BM``) and a foreign
company can list in New York under its home ISIN (Barrick ``CA``). Writers
therefore refuse to *change* an ISIN to one whose prefix does not fit the
exchange unless the caller confirms it with ``allow_foreign_isin``; an ISIN
already on disk is left alone so unrelated edits (a grouping) still save.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Optional

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# London: UK plus the Crown Dependencies, Ireland and Luxembourg (fund and ETC
# domiciles) and XS (international debt/ETC issues). Kept in step with
# allotmint-pro's data-quality ``LSE_ISIN_PREFIXES``.
_LSE_PREFIXES: FrozenSet[str] = frozenset({"GB", "IE", "JE", "GG", "IM", "LU", "XS"})
_US_PREFIXES: FrozenSet[str] = frozenset({"US"})
_DE_PREFIXES: FrozenSet[str] = frozenset({"DE"})

# App exchange code -> ISIN country prefixes expected for a home listing.
# Exchanges not listed here are not checked.
EXCHANGE_ISIN_PREFIXES: Dict[str, FrozenSet[str]] = {
    "L": _LSE_PREFIXES,
    "LSE": _LSE_PREFIXES,
    "UK": _LSE_PREFIXES,
    "N": _US_PREFIXES,
    "NYSE": _US_PREFIXES,
    "NASDAQ": _US_PREFIXES,
    "US": _US_PREFIXES,
    "DE": _DE_PREFIXES,
    "XETRA": _DE_PREFIXES,
    "F": _DE_PREFIXES,
    "PARIS": frozenset({"FR"}),
    "TO": frozenset({"CA"}),
    "TSX": frozenset({"CA"}),
    "ASX": frozenset({"AU"}),
}


class ForeignIsinError(ValueError):
    """An ISIN change whose country prefix does not fit the listing exchange."""


def normalise_isin(value: Any) -> Optional[str]:
    """Upper-cased, stripped ISIN text, or ``None`` when blank or not a string."""
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    return text or None


def isin_fits_exchange(isin: Any, exchange: Any) -> Optional[bool]:
    """Whether ``isin``'s country prefix is expected on ``exchange``.

    ``None`` when there is nothing to judge: a blank or malformed ISIN (e.g.
    the ``"-"`` placeholder) or an exchange without an expected-prefix entry.
    """
    text = normalise_isin(isin)
    if text is None or not ISIN_RE.match(text) or not isinstance(exchange, str):
        return None
    expected = EXCHANGE_ISIN_PREFIXES.get(exchange.strip().upper())
    if expected is None:
        return None
    return text[:2] in expected


def check_isin_change(
    existing_isin: Any,
    new_isin: Any,
    exchange: Any,
    *,
    allow_foreign_isin: bool = False,
) -> None:
    """Raise :class:`ForeignIsinError` if ``new_isin`` would replace ``existing_isin`` with a misfit.

    Nothing is checked when the ISIN is unchanged (case-insensitively), being
    removed, or when ``allow_foreign_isin`` is set.
    """
    new = normalise_isin(new_isin)
    if allow_foreign_isin or new is None or new == normalise_isin(existing_isin):
        return
    if isin_fits_exchange(new, exchange) is False:
        expected = ", ".join(sorted(EXCHANGE_ISIN_PREFIXES[str(exchange).strip().upper()]))
        raise ForeignIsinError(
            f"ISIN {new} has country prefix {new[:2]}, which does not fit exchange {exchange} "
            f"(expected {expected}); existing ISIN {normalise_isin(existing_isin) or 'none'}. "
            "If the ISIN is right (e.g. an overseas company trading via depositary interests), "
            "set allow_foreign_isin."
        )


__all__ = [
    "EXCHANGE_ISIN_PREFIXES",
    "ForeignIsinError",
    "ISIN_RE",
    "check_isin_change",
    "isin_fits_exchange",
    "normalise_isin",
]
