"""Optional sub-asset classes for Equity, Bond and Commodity holdings (#9543, #9653).

The strategy page lets an owner set a target either for a whole asset class
("bond: 40%") or for its sub-classes ("long_gilts: 10%, short_gilts: 20%").
The sub-class keys match the asset-class blocks of allotmint-pro's
``backtest_portfolio`` MCP tool, so the app and the backtests share one
vocabulary (``overseas_government`` has no backtest block yet).

Equity has one named sub-class, ``small_cap_value`` (the Golden Butterfly's
tilt), and a remainder, ``broad_equity``, for everything else. The backtest
calls that remainder plain ``equity``; here the whole-class key cannot double
as a sub-class, so :func:`policy_targets` renames it when a weight set mixes
``equity`` with an equity sub-class.

:func:`resolve_sub_asset_class` decides an instrument's sub-class:

1. An explicit ``sub_asset_class`` on the instrument metadata wins, then one
   in ``instrument_classification_overrides.json``. An override that does not
   belong to the instrument's asset class is logged and ignored.
2. Otherwise it is derived from data that already exists: ``fund_facts``
   (``effective_duration_years``, ``maturity_band``, ``index``) and the name.
   Gilts are banded by duration: under 3 years short, 3-10 intermediate,
   over 10 long. Equity whose name or index says "small cap ... value" is
   ``small_cap_value``; all other equity is ``broad_equity``.
3. ``None`` when nothing matches; callers keep the holding in its parent
   class and report it rather than dropping it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from backend.common.instrument_classification import BOND, COMMODITY, EQUITY, cached_classification_overrides
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BROAD_EQUITY = "broad_equity"
SMALL_CAP_VALUE = "small_cap_value"
LONG_GILTS = "long_gilts"
INTERMEDIATE_GILTS = "intermediate_gilts"
SHORT_GILTS = "short_gilts"
INDEX_LINKED = "index_linked"
OVERSEAS_GOVERNMENT = "overseas_government"
CORPORATE_BONDS = "corporate_bonds"
GOLD = "gold"
OTHER_COMMODITIES = "other_commodities"
#: The other-commodities key before #9718. It is also an alias of the whole
#: Commodity class, so it is read as the sub-class only beside another
#: commodity sub-class (:func:`legacy_target_key`) or as an instrument override.
LEGACY_OTHER_COMMODITIES = "commodities"

#: Sub-classes of each splittable asset class, in display order.
SUB_ASSET_CLASSES: dict[str, tuple[str, ...]] = {
    EQUITY: (BROAD_EQUITY, SMALL_CAP_VALUE),
    BOND: (LONG_GILTS, INTERMEDIATE_GILTS, SHORT_GILTS, INDEX_LINKED, OVERSEAS_GOVERNMENT, CORPORATE_BONDS),
    COMMODITY: (GOLD, OTHER_COMMODITIES),
}

#: Parent asset class of each sub-class key.
SUB_ASSET_CLASS_PARENT: dict[str, str] = {sub: parent for parent, subs in SUB_ASSET_CLASSES.items() for sub in subs}

#: The sub-class that holds a split class's members with no named sub-class.
#: In backtest weights the whole-class key plays that role (``equity`` beside
#: ``small_cap_value``); see :func:`policy_targets`.
REMAINDER_SUB_CLASS: dict[str, str] = {EQUITY: BROAD_EQUITY}

SUB_ASSET_CLASS_LABELS: dict[str, str] = {
    BROAD_EQUITY: "Broad equity",
    SMALL_CAP_VALUE: "Small-cap value",
    LONG_GILTS: "Long gilts",
    INTERMEDIATE_GILTS: "Intermediate gilts",
    SHORT_GILTS: "Short gilts / ultrashort",
    INDEX_LINKED: "Index-linked",
    OVERSEAS_GOVERNMENT: "Overseas government",
    CORPORATE_BONDS: "Corporate / credit",
    GOLD: "Gold",
    OTHER_COMMODITIES: "Other commodities",
}

#: Gilt duration bands in years: below SHORT_MAX is short, above LONG_MIN long.
SHORT_GILT_MAX_YEARS = 3.0
LONG_GILT_MIN_YEARS = 10.0

# "Inflatin" is a real misspelling in an iShares product name (GILG.L).
_INDEX_LINKED_RE = re.compile(r"inflati?on[- ]linked|inflatin|index[- ]linked|\blinkers?\b|\bTIPS\b", re.IGNORECASE)
_ULTRASHORT_RE = re.compile(r"ultra[- ]?short", re.IGNORECASE)
_GILT_RE = re.compile(r"\bgilts?\b|\bUK (government|govt|conventional)\b", re.IGNORECASE)
_CREDIT_RE = re.compile(r"\bcorp(orates?)?\b|\bcredit\b|\binvestment grade\b|\bhigh yield\b|\bloans?\b", re.IGNORECASE)
# "Income" alone means credit (TwentyFour Income Fund, TFIF.L) but is weaker
# than a government issuer: "Global Government Bond Income" is sovereign (#9636).
_INCOME_RE = re.compile(r"\bincome\b", re.IGNORECASE)
_GOVERNMENT_RE = re.compile(r"\bgovernment\b|\bgovt\b|\btreasur(y|ies)\b|\bbunds?\b|\bsovereign\b", re.IGNORECASE)
_GOLD_RE = re.compile(r"\bgold\b", re.IGNORECASE)
# "Small Cap Value", "Small-Cap 600 Value", "SmallCap Value Weighted".
_SMALL_CAP_VALUE_RE = re.compile(r"\bsmall[- ]?cap\b[\w\s&-]{0,20}?\bvalue\b", re.IGNORECASE)
# "0-5yr", "1-10 Years", "15+ Year": maturity range in a band label or name.
_MATURITY_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)|(\+))\s*(?:years?|yrs?)\b", re.IGNORECASE)


def _fact(meta: Mapping[str, Any], key: str) -> Any:
    """Value of ``fund_facts[key]``, unwrapping ``{"value": ...}`` entries."""
    facts = meta.get("fund_facts")
    if not isinstance(facts, Mapping):
        return None
    value = facts.get(key)
    return value.get("value") if isinstance(value, Mapping) else value


def _fact_text(meta: Mapping[str, Any], key: str) -> str:
    value = _fact(meta, key)
    return value.strip() if isinstance(value, str) else ""


def _duration_years(meta: Mapping[str, Any]) -> Optional[float]:
    value = _fact(meta, "effective_duration_years")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _maturity_years(text: str) -> Optional[float]:
    """Representative maturity of a range label: the midpoint, or the floor of "N+"."""
    match = _MATURITY_RANGE_RE.search(text)
    if match is None:
        return None
    low = float(match.group(1))
    if match.group(3):
        return low
    return (low + float(match.group(2))) / 2.0


def _gilt_band(years: float) -> str:
    if years < SHORT_GILT_MAX_YEARS:
        return SHORT_GILTS
    if years > LONG_GILT_MIN_YEARS:
        return LONG_GILTS
    return INTERMEDIATE_GILTS


def _gilt_sub_class(meta: Mapping[str, Any], text: str) -> Optional[str]:
    """Band a conventional gilt fund by duration, then maturity band, then name."""
    years = _duration_years(meta)
    if years is None:
        years = _maturity_years(_fact_text(meta, "maturity_band")) or _maturity_years(text)
    return _gilt_band(years) if years is not None else None


def derive_bond_sub_class(meta: Mapping[str, Any]) -> Optional[str]:
    """Sub-class of a bond instrument from its fund facts and name, or ``None``."""
    text = " ".join(
        part
        for part in (
            str(meta.get("name") or ""),
            _fact_text(meta, "index"),
            _fact_text(meta, "maturity_band"),
        )
        if part
    )
    if _INDEX_LINKED_RE.search(text):
        return INDEX_LINKED
    if _ULTRASHORT_RE.search(text):
        return SHORT_GILTS
    if _GILT_RE.search(text):
        return _gilt_sub_class(meta, text)
    if _CREDIT_RE.search(text):
        return CORPORATE_BONDS
    if _GOVERNMENT_RE.search(text):
        return OVERSEAS_GOVERNMENT
    if _INCOME_RE.search(text):
        return CORPORATE_BONDS
    return None


def derive_commodity_sub_class(meta: Mapping[str, Any]) -> str:
    """``gold`` for a gold product, otherwise ``other_commodities``."""
    text = f"{meta.get('name') or ''} {_fact_text(meta, 'index')}"
    return GOLD if _GOLD_RE.search(text) else OTHER_COMMODITIES


def derive_equity_sub_class(meta: Mapping[str, Any]) -> str:
    """``small_cap_value`` for a small-cap value product, otherwise ``broad_equity``."""
    text = f"{meta.get('name') or ''} {_fact_text(meta, 'index')}"
    return SMALL_CAP_VALUE if _SMALL_CAP_VALUE_RE.search(text) else BROAD_EQUITY


def legacy_target_key(key: str, keys: frozenset[str]) -> str:
    """``key`` with the pre-#9718 ``commodities`` sub-class renamed, reading it as before.

    ``commodities`` beside another commodity sub-class (``gold``, even at 0)
    was the "other commodities" sub-class and becomes ``other_commodities``.
    On its own it named the whole Commodity class and is returned unchanged,
    for the caller to resolve as the class alias. ``keys`` are the lower-cased
    keys of the same target set; any other key is returned unchanged.
    """
    if key != LEGACY_OTHER_COMMODITIES:
        return key
    siblings = any(other != key and SUB_ASSET_CLASS_PARENT.get(other) == COMMODITY for other in keys)
    return OTHER_COMMODITIES if siblings else key


def policy_targets(weights: Mapping[str, float]) -> dict[str, float]:
    """``weights`` with a whole-class key renamed to its remainder sub-class.

    Backtest and plan weights write the Golden Butterfly as ``equity: 20,
    small_cap_value: 20``. A policy cannot target Equity both as a whole and
    by sub-class, so ``equity`` becomes ``broad_equity`` whenever an equity
    sub-class is also present. The backtest's ``commodities`` block beside
    ``gold`` becomes ``other_commodities`` (:func:`legacy_target_key`). Other
    weights are returned unchanged.
    """
    keys = frozenset(weights)
    result: dict[str, float] = {}
    for key, pct in weights.items():
        target = legacy_target_key(key, keys)
        result[target] = result.get(target, 0.0) + pct
    for parent, remainder in REMAINDER_SUB_CLASS.items():
        if parent in result and any(SUB_ASSET_CLASS_PARENT.get(key) == parent for key in result):
            result[remainder] = result.get(remainder, 0.0) + result.pop(parent)
    return result


def _valid_override(value: Any, asset_class: str, ticker: str) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    # An override is always a sub-class, so the pre-#9718 key needs no sibling.
    if key == LEGACY_OTHER_COMMODITIES:
        key = OTHER_COMMODITIES
    if SUB_ASSET_CLASS_PARENT.get(key) == asset_class:
        return key
    logger.warning(
        "Ignoring sub_asset_class override %s for %s; expected one of %s",
        sanitise_log_value(value),
        sanitise_log_value(ticker),
        sanitise_log_value(", ".join(SUB_ASSET_CLASSES[asset_class])),
    )
    return None


def resolve_sub_asset_class(meta: Mapping[str, Any], asset_class: Optional[str]) -> Optional[str]:
    """Return the sub-class of an instrument of canonical ``asset_class``, if any."""
    if asset_class not in SUB_ASSET_CLASSES:
        return None
    ticker = str(meta.get("ticker") or "").strip().upper()
    explicit = _valid_override(meta.get("sub_asset_class"), asset_class, ticker)
    if explicit is not None:
        return explicit
    override = cached_classification_overrides().get(ticker, {}) if ticker else {}
    explicit = _valid_override(override.get("sub_asset_class"), asset_class, ticker)
    if explicit is not None:
        return explicit
    if asset_class == BOND:
        return derive_bond_sub_class(meta)
    if asset_class == EQUITY:
        return derive_equity_sub_class(meta)
    return derive_commodity_sub_class(meta)
