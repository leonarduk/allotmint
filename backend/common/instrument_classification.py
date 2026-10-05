"""Derive ``asset_class`` and an exposure-based ``sector`` for instruments.

Instrument metadata comes from several sources (Hargreaves Lansdown exports,
Yahoo Finance, hand edits) that disagree on vocabulary and often record a
fund's *issuer* sector instead of its exposure: a Vanguard or iShares ETF is
filed under "Financials" because the fund manager is a financial company. See
issue #9196.

:func:`classify_instrument` is the single, repeatable rule set:

1. A manual override (``{data_root}/instrument_classification_overrides.json``)
   always wins.
2. Otherwise ``asset_class`` is derived from the instrument type, name and
   provider category/sector, in that priority order.
3. For funds, trusts and other non-company products, a sector that is the
   issuer's (Financials, Financial Services, Miscellaneous) or contradicts the
   derived asset class is replaced by an exposure label (``"Multi-sector"``
   for equity funds, ``"Fixed Income"`` for bond funds, ...). Company shares
   keep their sector.

It is applied when metadata is fetched from Yahoo and by
``scripts/classify_instruments.py`` to backfill persisted metadata. The read
path (``get_instrument_meta``) never reclassifies.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

EQUITY = "equity"
BOND = "bond"
CASH = "cash"
COMMODITY = "commodity"
PROPERTY = "property"
MULTI_ASSET = "multi-asset"

#: Canonical ``asset_class`` values, in the order the issue lists them.
ASSET_CLASSES: tuple[str, ...] = (EQUITY, BOND, CASH, COMMODITY, PROPERTY, MULTI_ASSET)

#: Display label for each canonical ``asset_class`` (reports, charts).
ASSET_CLASS_LABELS: dict[str, str] = {
    EQUITY: "Equity",
    BOND: "Bond",
    CASH: "Cash",
    COMMODITY: "Commodity",
    PROPERTY: "Property",
    MULTI_ASSET: "Multi-asset",
}

#: Sector label a fund gets when its own sector is missing or the issuer's.
FUND_SECTOR_BY_ASSET_CLASS: dict[str, str] = {
    EQUITY: "Multi-sector",
    BOND: "Fixed Income",
    CASH: "Cash",
    COMMODITY: "Commodities",
    PROPERTY: "Real Estate",
    MULTI_ASSET: "Multi-asset",
}

OVERRIDES_FILENAME = "instrument_classification_overrides.json"

# Legacy/provider spellings of an asset class. Values that describe a wrapper
# rather than an exposure ("Fund", "ETF", "Index", ...) are deliberately absent:
# they say nothing about whether the fund holds shares, bonds or gold.
_ASSET_CLASS_ALIASES: dict[str, str] = {
    "equity": EQUITY,
    "equities": EQUITY,
    "stock": EQUITY,
    "stocks": EQUITY,
    "share": EQUITY,
    "shares": EQUITY,
    "bond": BOND,
    "bonds": BOND,
    "fixed income": BOND,
    "cash": CASH,
    "money market": CASH,
    "moneymarket": CASH,
    "commodity": COMMODITY,
    "commodities": COMMODITY,
    "property": PROPERTY,
    "real estate": PROPERTY,
    "multi-asset": MULTI_ASSET,
    "multi asset": MULTI_ASSET,
    "mixed assets": MULTI_ASSET,
    "allocation": MULTI_ASSET,
}

# Instrument types (HL ``instrumentType`` / Yahoo ``quoteType``) that are a
# pooled vehicle rather than a single company's shares.
_FUND_TYPES = frozenset({"ETF", "ETC", "ETP", "FUND", "MUTUALFUND", "INVESTMENT TRUST", "OEIC", "UNIT TRUST"})
_EQUITY_TYPES = frozenset({"EQUITY", "STOCK", "SHARE"})
_CASH_TYPES = frozenset({"CASH", "MONEYMARKET", "MONEY MARKET"})
_BOND_TYPES = frozenset({"BOND", "GILT"})
# Index, currency, crypto and derivative quote types have no asset class in
# this vocabulary; they are left unset (and flagged by MISSING_ASSET_CLASS if
# held) rather than forced into one.

_FUND_NAME_RE = re.compile(r"\b(UCITS|ETF|ETC|INVESTMENT TRUST|INV TRUST|OEIC|ICAV)\b|\bFUNDS?\b", re.IGNORECASE)

# Name/category keywords, checked in this order; the first match wins. Bond
# and cash words come before the equity index words so "MSCI ... Corporate
# Bond" is a bond fund. Bare "gold" is deliberately not a commodity keyword:
# "Gold Producers" ETFs hold mining shares.
_KEYWORD_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (CASH, re.compile(r"\bmoney market\b|\bliquidity fund\b|\bcash fund\b", re.IGNORECASE)),
    (
        COMMODITY,
        re.compile(
            r"\bphysical (gold|silver|platinum|palladium|precious|metals?)\b|\bETC\b|\bcommodit(y|ies)\b",
            re.IGNORECASE,
        ),
    ),
    (
        BOND,
        re.compile(
            r"\bbonds?\b|\bgilts?\b|\btreasur(y|ies)\b|\bfixed income\b|\binflation[- ]linked\b|\bcredit\b"
            r"|\bgovt\b|\bgovernment\b|\bcorporate\b",
            re.IGNORECASE,
        ),
    ),
    (PROPERTY, re.compile(r"\breal estate\b|\bproperty\b|\bREITs?\b", re.IGNORECASE)),
    (MULTI_ASSET, re.compile(r"\bmulti[- ]asset\b|\bmixed asset\b|\ballocation\b|\blifestrategy\b", re.IGNORECASE)),
    (
        EQUITY,
        re.compile(
            r"\bequit(y|ies)\b|\bstocks?\b|\bMSCI\b|\bFTSE\b|\bS&P\b|\bstoxx\b|\bnasdaq\b|\bdividend\b", re.IGNORECASE
        ),
    ),
)

# Sector values that belong to the fund's issuer (a fund manager is a
# financial company) rather than to what the fund holds.
_ISSUER_SECTORS = frozenset({"financials", "financial services", "financial", "miscellaneous", "unknown"})

# Sector values that name the wrapper, not the exposure. They also mark the
# instrument as a fund when its type is missing.
_WRAPPER_SECTORS = frozenset({"investment trust", "investment trusts", "etf", "etfs", "fund", "funds", "index"})

# Sector values that are really an asset-class label; on a fund they must
# agree with the derived asset class or they are replaced.
_SECTOR_ASSET_CLASS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(fixed income|bonds?)$", re.IGNORECASE), BOND),
    (re.compile(r"^commodit", re.IGNORECASE), COMMODITY),
    (re.compile(r"^cash$", re.IGNORECASE), CASH),
    (re.compile(r"^(real estate|property)$", re.IGNORECASE), PROPERTY),
    (re.compile(r"^multi[- ]?asset$", re.IGNORECASE), MULTI_ASSET),
)


def normalise_asset_class(value: Any) -> Optional[str]:
    """Return the canonical asset class for ``value`` or ``None``.

    ``None`` means the value is missing or names a wrapper ("Fund", "ETF")
    rather than an exposure.
    """
    if not isinstance(value, str):
        return None
    return _ASSET_CLASS_ALIASES.get(value.strip().lower())


def canonical_asset_class(value: Any) -> Optional[str]:
    """Return ``value`` as a canonical asset class, keeping unknown labels.

    Read-path helper for metadata persisted before #9196, which spelled asset
    classes "Equity"/"Bond"/"Commodity": those resolve to the same lowercase
    value as freshly classified records, so consumers that bucket or compare
    by asset class see one value whatever the stored casing. A label outside
    the vocabulary ("Fund", "Index") is returned stripped but unchanged so
    nothing is silently discarded; a missing or blank value returns ``None``.
    """
    canonical = normalise_asset_class(value)
    if canonical is not None:
        return canonical
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def resolve_instrument_type(meta: Mapping[str, Any]) -> Optional[str]:
    """Return ``instrument_type`` for ``meta``, falling back to its asset class.

    An explicit ``instrumentType``/``instrument_type`` is returned verbatim
    (providers use "ETF", "EQUITY", "Investment Trust", ...). Without one, the
    asset class stands in, canonicalised by :func:`canonical_asset_class` so a
    legacy "Equity" and a new "equity" record resolve identically.
    """
    explicit = meta.get("instrumentType") or meta.get("instrument_type")
    if explicit:
        return explicit
    return canonical_asset_class(meta.get("assetClass") or meta.get("asset_class"))


def _instrument_type(meta: Mapping[str, Any]) -> str:
    raw = meta.get("instrumentType") or meta.get("instrument_type") or ""
    return str(raw).strip().upper()


def _text(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key)
    return value.strip() if isinstance(value, str) else ""


def is_fund(meta: Mapping[str, Any]) -> bool:
    """True for ETFs, ETCs, mutual funds and investment trusts."""
    if _instrument_type(meta) in _FUND_TYPES or _text(meta, "sector").lower() in _WRAPPER_SECTORS:
        return True
    return bool(_FUND_NAME_RE.search(_text(meta, "name")))


def _keyword_asset_class(text: str) -> Optional[str]:
    if not text:
        return None
    for asset_class, pattern in _KEYWORD_RULES:
        if pattern.search(text):
            return asset_class
    return None


def _sector_asset_class(sector: str) -> Optional[str]:
    """Asset class a sector label implies ("Government Bond" -> bond), if any."""
    for pattern, asset_class in _SECTOR_ASSET_CLASS:
        if pattern.search(sector):
            return asset_class
    return _keyword_asset_class(sector)


def derive_asset_class(meta: Mapping[str, Any]) -> Optional[str]:
    """Derive the asset class from type, name and provider category/sector."""
    ticker = _text(meta, "ticker").upper()
    instrument_type = _instrument_type(meta)
    if ticker.startswith("CASH.") or instrument_type in _CASH_TYPES:
        return CASH

    name_class = _keyword_asset_class(_text(meta, "name"))
    fund = is_fund(meta)
    if fund or name_class in (COMMODITY, CASH):
        # A product's name says what it holds ("... Gilts ETF", "Physical
        # Gold"); fall back to the provider's category (Yahoo ``category``),
        # then a sector that is really an asset-class label.
        derived = (
            name_class or _keyword_asset_class(_text(meta, "category")) or _sector_asset_class(_text(meta, "sector"))
        )
        if derived is not None:
            return derived
        return EQUITY if fund else None

    if instrument_type in _EQUITY_TYPES:
        return EQUITY
    if instrument_type in _BOND_TYPES:
        return BOND
    return normalise_asset_class(meta.get("asset_class"))


def _fund_sector(sector: str, asset_class: str) -> Optional[str]:
    """Return a replacement sector for a fund, or ``None`` to keep ``sector``."""
    label = FUND_SECTOR_BY_ASSET_CLASS[asset_class]
    if not sector or sector.lower() in _ISSUER_SECTORS or sector.lower() in _WRAPPER_SECTORS:
        return label
    sector_class = _sector_asset_class(sector)
    if sector_class is not None and sector_class != asset_class:
        return label
    if asset_class != EQUITY and sector_class is None:
        # A gold ETC filed under "Materials" or a gilt fund under "Utilities":
        # an equity sector says nothing about a non-equity product.
        return label
    return None


def classify_instrument(
    meta: Mapping[str, Any],
    override: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return the classification fields to set on ``meta``.

    The result holds ``asset_class`` (when one can be determined) and
    ``sector`` (only when it should change). ``override`` values win.
    """
    override = override or {}
    result: dict[str, Any] = {}

    override_class = override.get("asset_class")
    asset_class = normalise_asset_class(override_class)
    if override_class is not None and asset_class is None:
        logger.warning(
            "Ignoring unrecognised asset_class override %s for %s; expected one of %s",
            sanitise_log_value(override_class),
            sanitise_log_value(meta.get("ticker")),
            sanitise_log_value(", ".join(ASSET_CLASSES)),
        )
    asset_class = asset_class or derive_asset_class(meta)
    if asset_class is not None:
        result["asset_class"] = asset_class

    override_sector = override.get("sector")
    if isinstance(override_sector, str) and override_sector.strip():
        result["sector"] = override_sector.strip()
    elif asset_class is not None and (is_fund(meta) or asset_class != EQUITY):
        sector = _fund_sector(_text(meta, "sector"), asset_class)
        if sector is not None:
            result["sector"] = sector
    return result


def apply_classification(
    meta: Mapping[str, Any],
    override: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return a copy of ``meta`` with :func:`classify_instrument` applied."""
    updated = dict(meta)
    updated.update(classify_instrument(meta, override))
    return updated


def overrides_path() -> Path:
    """Return the manual overrides file under the configured data root.

    Falls back to the bundled ``data/`` directory when no data root is
    configured, matching ``backend.common.instruments``.
    """
    data_root = config.data_root or Path(__file__).resolve().parents[2] / "data"
    return Path(data_root) / OVERRIDES_FILENAME


def load_classification_overrides(path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """Load ``{TICKER: {"asset_class": ..., "sector": ...}}`` overrides.

    A missing file means no overrides. A malformed file is logged and treated
    as empty so one bad edit cannot block metadata ingest.
    """
    target = path or overrides_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(
            "Ignoring unreadable classification overrides %s: %s",
            sanitise_log_value(str(target)),
            sanitise_log_value(exc),
        )
        return {}
    if not isinstance(payload, dict):
        logger.warning("Classification overrides %s is not a JSON object", sanitise_log_value(str(target)))
        return {}
    overrides: dict[str, dict[str, Any]] = {}
    for ticker, entry in payload.items():
        if isinstance(entry, dict) and not str(ticker).startswith("_"):
            overrides[str(ticker).strip().upper()] = entry
    return overrides


@lru_cache(maxsize=4)
def _overrides_snapshot(path: str, mtime_ns: int) -> dict[str, dict[str, Any]]:
    """Parse ``path`` once per modification time (see :func:`cached_classification_overrides`)."""
    del mtime_ns  # cache key only: a changed file is re-read
    return load_classification_overrides(Path(path))


def cached_classification_overrides() -> dict[str, dict[str, Any]]:
    """Return the configured overrides, re-reading the file only when it changes.

    Used on the metadata-ingest path, which classifies one instrument per
    call; a ``stat`` replaces a read-and-parse per instrument, and an edited
    file is still picked up without a restart. Callers must not mutate the
    returned mapping. :func:`clear_overrides_cache` resets it (tests).
    """
    target = overrides_path()
    try:
        mtime_ns = target.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning(
            "Ignoring unreadable classification overrides %s: %s",
            sanitise_log_value(str(target)),
            sanitise_log_value(exc),
        )
        return {}
    return _overrides_snapshot(str(target), mtime_ns)


def clear_overrides_cache() -> None:
    """Drop cached overrides so the next lookup re-reads the file."""
    _overrides_snapshot.cache_clear()
