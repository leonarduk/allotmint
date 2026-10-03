"""NAV and premium/discount for listed closed-end funds (UK investment trusts).

No free source publishes UK investment-trust NAVs in a form we may fetch
automatically. Yahoo's ``navPrice`` is empty for LSE trusts. The AIC's terms
forbid scraping. RNS announcements can be read on the web, but machine access
needs the paid LSEG feed. So NAVs come from pluggable :class:`NavProvider`
implementations, and the first ones are data-fed:

* :class:`CsvNavProvider` reads ``<data_root>/nav/navs.csv``. Each row is one
  NAV (``ticker,nav,currency,nav_date,source``), typically copied from the
  trust's RNS NAV announcement or factsheet.
* :class:`MetadataNavProvider` reads ``nav_per_share``/``nav_currency``/
  ``nav_as_of`` from the instrument metadata. These are the keys
  allotmint-pro's valuation profile also reads.

A licensed API can be added later as another provider without changing callers.
See ``docs/NAV_DISCOUNT.md``.

:func:`nav_discount` compares the most recent NAV with the close **on or just
before the NAV date**, not today's price. Both values are converted to GBP
explicitly: pence divide by 100 exactly, and other currencies use the cached FX
rate. A price/NAV ratio that only a pence/pound mix-up would explain is reported
as a unit error instead of a number.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from backend.common.currency import CurrencyNormaliser
from backend.common.instruments import get_instrument_meta
from backend.common.ttl_cache import TTLCache
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Metadata instrument types (lower-cased) that trade against a published NAV.
# The same set as allotmint-pro's valuation CLOSED_END_TYPES.
CLOSED_END_TYPES = frozenset(
    {"investment trust", "investment company", "closed-end fund", "closed end fund", "closedendfund", "vct"}
)

# Outside this price/NAV band the likeliest cause is a units error (pence vs
# pounds, or a wrong currency), not a real 80% discount or 400% premium.
MIN_PLAUSIBLE_RATIO = 0.2
MAX_PLAUSIBLE_RATIO = 5.0

CSV_COLUMNS = ("ticker", "nav", "currency", "nav_date", "source")

PriceLookup = Callable[[str, str, date], Tuple[Optional[float], Optional[date]]]
FxLookup = Callable[[str], Optional[float]]


@dataclass(frozen=True)
class NavRecord:
    """One NAV per share as published, in ``currency`` (``GBX`` = pence)."""

    nav: float
    currency: str
    nav_date: Optional[date]
    source: str


class NavProvider(Protocol):
    name: str

    def latest_nav(self, ticker: str) -> Optional[NavRecord]: ...


@dataclass
class NavDiscount:
    ticker: str
    applicable: bool
    reason: Optional[str] = None
    nav: Optional[float] = None
    nav_currency: Optional[str] = None
    nav_gbp: Optional[float] = None
    nav_date: Optional[str] = None
    nav_source: Optional[str] = None
    price_gbp: Optional[float] = None
    price_date: Optional[str] = None
    # price / nav - 1 as a fraction (-0.12 = 12% discount) and as a percentage.
    premium_discount: Optional[float] = None
    premium_discount_pct: Optional[float] = None
    fx_converted: bool = False
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ───────────────────────────── providers ─────────────────────────────


def _parse_positive(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _newer(candidate: NavRecord, current: Optional[NavRecord]) -> bool:
    """A dated NAV beats an undated one. Between two dated NAVs the later date wins."""
    if current is None:
        return True
    if candidate.nav_date is None:
        return False
    return current.nav_date is None or candidate.nav_date >= current.nav_date


def _default_csv_path() -> Path:
    return Path(config.data_root or "data") / "nav" / "navs.csv"


def _record_from_row(row: Dict[str, Any], line: int, path: Path) -> Optional[NavRecord]:
    nav = _parse_positive(row.get("nav"))
    currency = str(row.get("currency") or "").strip()
    if nav is None or not currency:
        # A NAV without its unit is ambiguous (pence vs pounds), so it is dropped
        # and logged rather than guessed.
        logger.warning(
            "Skipping %s line %s: needs a positive nav and an explicit currency",
            sanitise_log_value(path),
            sanitise_log_value(line),
        )
        return None
    source = str(row.get("source") or "").strip() or "manual"
    return NavRecord(nav=nav, currency=currency, nav_date=_parse_date(row.get("nav_date")), source=source)


def load_nav_csv(path: Path) -> Dict[str, NavRecord]:
    """Return the latest NAV per upper-cased ticker in ``path`` (``{}`` if it is absent)."""
    if not path.is_file():
        return {}
    latest: Dict[str, NavRecord] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            ticker = str(row.get("ticker") or "").strip().upper()
            record = _record_from_row(row, line, path) if ticker else None
            if record is not None and _newer(record, latest.get(ticker)):
                latest[ticker] = record
    return latest


class CsvNavProvider:
    """NAVs recorded by hand (or by an import job) in ``<data_root>/nav/navs.csv``."""

    name = "csv"

    def __init__(self, path_factory: Callable[[], Path] = _default_csv_path, ttl_seconds: float = 300) -> None:
        self._path_factory = path_factory
        self._cache: TTLCache[Dict[str, NavRecord]] = TTLCache(ttl_seconds, name="nav_csv")

    def latest_nav(self, ticker: str) -> Optional[NavRecord]:
        path = self._path_factory()
        # The mtime is part of the key, so an edited file is re-read at once.
        mtime = path.stat().st_mtime_ns if path.is_file() else None
        navs = self._cache.get_or_build((str(path), mtime), lambda: load_nav_csv(path))
        return navs.get(ticker.upper())


class MetadataNavProvider:
    """``nav_per_share`` / ``nav_currency`` / ``nav_as_of`` on the instrument metadata."""

    name = "metadata"

    def latest_nav(self, ticker: str) -> Optional[NavRecord]:
        meta = get_instrument_meta(ticker) or {}
        nav = _parse_positive(meta.get("nav_per_share"))
        currency = str(meta.get("nav_currency") or "").strip()
        if nav is None:
            return None
        if not currency:
            logger.warning("Ignoring metadata NAV for %s: nav_currency is not set", sanitise_log_value(ticker))
            return None
        return NavRecord(nav=nav, currency=currency, nav_date=_parse_date(meta.get("nav_as_of")), source="metadata")


def latest_nav(ticker: str, providers: Iterable[NavProvider]) -> Optional[NavRecord]:
    """The most recent NAV any provider has for ``ticker``. Ties go to the earlier provider."""
    best: Optional[NavRecord] = None
    for provider in providers:
        record = provider.latest_nav(ticker)
        if record is None:
            continue
        same_date = best is not None and record.nav_date == best.nav_date
        if not same_date and _newer(record, best):
            best = record
    return best


# ───────────────────────────── discount ─────────────────────────────


def is_closed_end(meta: Dict[str, Any]) -> bool:
    kind = meta.get("instrumentType") or meta.get("instrument_type") or ""
    return str(kind).strip().lower() in CLOSED_END_TYPES


def nav_to_gbp(nav: float, currency: str, fx_lookup: FxLookup) -> Tuple[Optional[float], bool]:
    """``(nav in GBP, whether FX was applied)``. ``None`` when no FX rate is cached."""
    normaliser = CurrencyNormaliser.from_raw(currency)
    if normaliser.is_pence:
        return nav * normaliser.pence_factor, False
    if normaliser.canonical == "GBP":
        return nav, False
    rate = fx_lookup(normaliser.canonical)
    if rate is None or not math.isfinite(rate) or rate <= 0:
        return None, True
    return nav * rate, True


def _split_ticker(ticker: str) -> Tuple[str, str]:
    symbol, _, exchange = ticker.upper().partition(".")
    return symbol, exchange or "L"


def default_price_lookup(symbol: str, exchange: str, on: date) -> Tuple[Optional[float], Optional[date]]:
    """The cached GBP close on ``on`` or up to four days before, and the date it is from.

    Uses the holdings pricing path (scaling overrides included) inside
    ``cache_only()``, so a request never triggers a live price fetch.
    """
    from backend.common.holding_utils import _get_dated_price_for_date_scaled
    from backend.timeseries.cache import cache_only

    with cache_only():
        price, _source, row_date = _get_dated_price_for_date_scaled(symbol, exchange, on)
    return price, row_date


def default_fx_lookup(currency: str) -> Optional[float]:
    from backend.timeseries.cache import cached_fx_rate_to_gbp

    return cached_fx_rate_to_gbp(currency)


def default_providers() -> Sequence[NavProvider]:
    return (_CSV_PROVIDER, MetadataNavProvider())


def _apply_record(result: NavDiscount, record: NavRecord, fx_lookup: FxLookup) -> None:
    result.nav = record.nav
    result.nav_currency = record.currency
    result.nav_date = record.nav_date.isoformat() if record.nav_date else None
    result.nav_source = record.source
    nav_gbp, result.fx_converted = nav_to_gbp(record.nav, record.currency, fx_lookup)
    result.nav_gbp = round(nav_gbp, 6) if nav_gbp is not None else None
    if result.fx_converted:
        result.warnings.append(f"NAV converted from {record.currency} to GBP at the latest cached FX rate.")


def _apply_price(result: NavDiscount, price: Optional[float], price_date: Optional[date]) -> None:
    result.price_gbp = round(price, 6) if price is not None else None
    result.price_date = price_date.isoformat() if price_date else None
    if price is None or result.nav_gbp is None:
        result.reason = "No cached price near the NAV date." if price is None else "No cached FX rate for the NAV."
        return
    ratio = price / result.nav_gbp
    if not MIN_PLAUSIBLE_RATIO <= ratio <= MAX_PLAUSIBLE_RATIO:
        result.reason = (
            f"Price/NAV ratio {ratio:.3g} is implausible; check the NAV's currency (GBX pence vs GBP pounds)."
        )
        return
    result.premium_discount = round(ratio - 1, 4)
    result.premium_discount_pct = round((ratio - 1) * 100, 2)


def nav_discount(
    ticker: str,
    *,
    providers: Optional[Sequence[NavProvider]] = None,
    price_lookup: PriceLookup = default_price_lookup,
    fx_lookup: FxLookup = default_fx_lookup,
    today: Optional[date] = None,
) -> NavDiscount:
    """NAV, price on the NAV date and premium/discount for one closed-end fund.

    Always returns a result. When no number can be given, ``reason`` says why
    (not a closed-end fund, no NAV recorded, no price, implausible units).
    """
    ticker = ticker.strip().upper()
    if not is_closed_end(get_instrument_meta(ticker) or {}):
        return NavDiscount(
            ticker=ticker,
            applicable=False,
            reason="Not classified as an investment trust / closed-end fund in instrument metadata "
            "(instrument_type), so no NAV discount applies.",
        )
    result = NavDiscount(ticker=ticker, applicable=True)
    record = latest_nav(ticker, providers if providers is not None else default_providers())
    if record is None:
        result.reason = "No NAV recorded for this fund; add one to nav/navs.csv in the data root."
        return result
    _apply_record(result, record, fx_lookup)
    if record.nav_date is None:
        result.warnings.append("NAV has no date; compared with the latest cached close instead.")
    symbol, exchange = _split_ticker(ticker)
    price, price_date = price_lookup(symbol, exchange, record.nav_date or today or date.today())
    _apply_price(result, price, price_date)
    return result


_CSV_PROVIDER = CsvNavProvider()
