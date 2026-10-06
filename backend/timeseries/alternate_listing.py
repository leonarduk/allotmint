"""Alternate exchange listing as an instrument's price source (#9657).

Some securities trade on more than one exchange, and Yahoo's history for the
listing we hold can decay while another venue's stays complete. AIGE.L
(WisdomTree Energy ETC, USD on the LSE) is the first case: Yahoo now returns
only the current day for it, while AIGE.MI (Borsa Italiana, EUR, same ISIN)
has full history from 2008. Stored AIGE.L closes agree with AIGE.MI converted
to USD to well within 1%.

An instrument's metadata (``instruments/<EX>/<SYM>.json``) may therefore carry
an optional top-level ``price_source`` block::

    "price_source": {
      "ticker": "AIGE",
      "exchange": "MI",
      "currency": "EUR",
      "mode": "primary",
      "rationale": "why this listing",
      "reviewed": "2026-10-06"
    }

``ticker``/``exchange``
    The other listing, as an app exchange code with a Yahoo suffix
    (``get_yahoo_suffix``). It must not be the instrument's own listing, and
    it needs no instrument file of its own.
``currency`` (optional)
    What that listing is quoted in; defaults to ``EXCHANGE_TO_CCY`` for the
    exchange. Yahoo's reported currency must match it, or the fetch is refused.
``mode`` (optional)
    ``"fill_gaps"`` (the default) or ``"primary"``; see *Fetch order* below.
``rationale``/``reviewed``
    Optional free text and ISO date, as for ``proxy``.

This is not the ``proxy`` block (``backend.common.instrument_proxy``). A proxy
is a *different* series whose returns stand in for the instrument before its
own history starts, applied at read time for backtests. ``price_source`` is
the *same* security on another venue, and its converted closes are stored as
the instrument's own prices.

Conversion
----------
The listing is fetched on the raw traded basis (``YAHOO_HISTORY_KWARGS``),
then each OHLC value is converted to the instrument's currency with the stored
FX history (``timeseries/fx/<CCY>.parquet``, ``Rate`` = GBP per unit, read by
``load_fx_history`` without fetching)::

    price_target = price_source * rate_source / rate_target   # same date

GBP has rate 1. A date without its own rate takes the latest earlier rate at
most :data:`FX_FFILL_DAYS` calendar days before it. Dates with no rate in that
window are dropped: no rate or price is invented. Pence currencies are not
supported on either side, because their stored closes depend on
``scaling_overrides.json``. Converted prices are rounded to six significant
figures like every fetcher, ``Volume`` is the other listing's, ``Ticker`` is
the instrument's own, and ``Source``
is :func:`backend.timeseries.source_basis.alternate_listing_source`, e.g.
``Yahoo:AIGE.MI→USD``. Dividends and splits on the other listing are never
stored for the instrument; if Yahoo reports any, they are logged.

Merging with the native listing
-------------------------------
:func:`apply_price_source` runs after the normal provider chain for the
instrument's own listing. The native reference is the stored series without
earlier converted rows, overlaid by the freshly fetched native rows. For each
date:

* the native row is kept when it has a real close and volume
  (``Close > 0`` and ``Volume > 0``);
* a missing date or a missing close is filled from the converted row;
* a native close with zero/missing volume (a stale or placeholder print on a
  day nothing traded on the native venue) is replaced only when the converted
  row traded (``Volume > 0``) *and* agrees with it within
  ``source_basis.BASIS_TOLERANCE``. Swapping one untraded print for another
  only churns the stored series; and when the two disagree by more, one of
  them is wrong and nothing says which (AIGE.MI repeats a stale 6.525 EUR
  close with nominal volume through July 2012), so the stored close stays.

Before any converted row is used, the whole converted window must pass
``source_basis.same_basis`` on shared dates against the first of these that
shares a date with it: the traded-basis native rows (not Stooq, which
``same_basis`` holds to 0.5% on every date), all native rows, then the stored
window including earlier converted rows (so a refresh window with no native
close is still checked for continuity). If the check fails, nothing converted
is used. If no stored close shares a date, the declared listing is trusted.

Fetch order (#9712)
-------------------
With ``"fill_gaps"`` the instrument's own provider chain (Yahoo, Stooq, Alpha
Vantage, FT) runs first and the converted listing only fills what it lacks.

With ``"primary"`` the converted listing is fetched first. The native chain
then runs only over the weekdays in the window that have no close in either the
converted listing or the stored series, and not at all when there are none. Use
it for a listing whose own history has decayed (AIGE.L), where the native chain
returns nothing but ERRORs and timeouts. The merge rule and basis check above
apply unchanged, to the stored series and whatever native rows are fetched, so
a stored native row with a real close is still kept. The trade-off: on a date
the converted listing covers, a native close that is not yet stored is never
fetched, so the converted row is used. If the converted listing cannot be used
at all (fetch or conversion failure, or a basis refusal), the whole window is
fetched natively.

Either way, while the native chain runs for an instrument with a valid
``price_source``, the providers' own "no data" ERRORs and WARNINGs (including
yfinance's "possibly delisted") are logged at INFO: the alternate listing is
what prices the instrument, so they are not faults. Stooq and Alpha Vantage
warnings about rate limits and cooldowns affect every ticker and keep their
level. The downgrade is scoped to the calling context (:data:`_QUIET_NATIVE`),
so concurrent fetches for other instruments are not affected.

Because converted rows were checked here against the stored series,
``source_basis.compatible_rows`` does not re-check them in
``_rolling_cache``: gap-only rows share no dates with the cache, so that check
would always refuse them. The zero-volume spike guard still applies when the
series is read.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterator, Mapping, Optional

import pandas as pd
import yfinance as yf

from backend.common.instruments import get_instrument_meta
from backend.logging_setup import sanitise_log_value
from backend.timeseries.fetch_yahoo_timeseries import (
    YAHOO_HISTORY_KWARGS,
    _build_full_ticker,
    _history_currency,
    get_yahoo_suffix,
    normalize_history,
)
from backend.timeseries.source_basis import (
    BASIS_TOLERANCE,
    DIVIDEND_ADJUSTED_SOURCES,
    alternate_listing_source,
    basis_ratio,
    is_alternate_listing_source,
    same_basis,
)
from backend.utils.timeseries_helpers import PRICE_COLUMNS, STANDARD_COLUMNS, round_price_columns

logger = logging.getLogger(__name__)

# Longest gap, in calendar days, an FX rate is carried forward over (a long
# weekend plus a holiday). Anything longer drops the price rather than guess.
FX_FFILL_DAYS = 5

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,11}$")
_ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_PENCE_CODES = frozenset({"GBX"})

# ``price_source.mode`` values (#9712); see the module docs.
MODE_FILL_GAPS = "fill_gaps"
MODE_PRIMARY = "primary"
PRICE_SOURCE_MODES = (MODE_FILL_GAPS, MODE_PRIMARY)


@dataclass(frozen=True)
class PriceSource:
    """Parsed ``price_source`` block."""

    ticker: str
    exchange: str
    currency: str
    mode: str = MODE_FILL_GAPS

    @property
    def full_ticker(self) -> str:
        return f"{self.ticker}.{self.exchange}"


def _default_currency(exchange: str) -> Optional[str]:
    # Imported here: ``cache`` imports ``fetch_meta_timeseries``, which imports this module.
    from backend.timeseries.cache import EXCHANGE_TO_CCY

    return EXCHANGE_TO_CCY.get(exchange)


def _is_iso_currency(code: Any) -> bool:
    """A 3-letter currency code that is not a pence code (``GBp`` upper-cases to ``GBP``)."""
    if not isinstance(code, str) or code.strip() != code.strip().upper():
        return False
    text = code.strip()
    return bool(_ISO_CURRENCY_RE.match(text)) and text not in _PENCE_CODES


def _split_ticker(raw: Any, exchange: str) -> str:
    text = str(raw or "").strip().upper()
    suffix = f".{exchange}"
    return text[: -len(suffix)] if exchange and text.endswith(suffix) else text


def validate_price_source(meta: Mapping[str, Any] | None, *, own: str = "") -> list[str]:
    """Problems with ``meta["price_source"]``, one message each; ``[]`` when valid or absent.

    ``own`` is the instrument's ``SYM.EX``, which the block must not point at.
    """
    raw = (meta or {}).get("price_source")
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return ["price_source must be a JSON object"]
    problems: list[str] = []
    exchange = str(raw.get("exchange") or "").strip().upper()
    try:
        get_yahoo_suffix(exchange)
    except ValueError:
        problems.append(f"price_source: unsupported exchange {raw.get('exchange')!r}")
    ticker = _split_ticker(raw.get("ticker"), exchange)
    if not _SYMBOL_RE.match(ticker):
        problems.append(f"price_source: invalid ticker {raw.get('ticker')!r}")
    elif own and f"{ticker}.{exchange}" == own.strip().upper():
        problems.append("price_source: points at the instrument's own listing")
    currency = raw.get("currency") or _default_currency(exchange)
    if not _is_iso_currency(currency):
        problems.append(f"price_source: currency {currency!r} is not a supported ISO code (pence is not supported)")
    target = (meta or {}).get("currency")
    if not _is_iso_currency(target):
        problems.append(f"price_source: instrument currency {target!r} is not a supported ISO code")
    mode = raw.get("mode")
    if mode is not None and mode not in PRICE_SOURCE_MODES:
        problems.append(f"price_source: mode {mode!r} is not one of {', '.join(PRICE_SOURCE_MODES)}")
    return problems


def parse_price_source(meta: Mapping[str, Any] | None, *, own: str = "") -> PriceSource | None:
    """Typed ``price_source``, or ``None`` when absent. Raises ``ValueError`` when invalid."""
    problems = validate_price_source(meta, own=own)
    if problems:
        raise ValueError("; ".join(problems))
    raw = (meta or {}).get("price_source")
    if raw is None:
        return None
    exchange = str(raw["exchange"]).strip().upper()
    currency = str(raw.get("currency") or _default_currency(exchange)).strip()
    return PriceSource(
        ticker=_split_ticker(raw["ticker"], exchange),
        exchange=exchange,
        currency=currency,
        mode=raw.get("mode") or MODE_FILL_GAPS,
    )


# ──────────────────────────────────────────────────────────────
# Native misses for an instrument priced from another listing
# ──────────────────────────────────────────────────────────────
# Set while the native chain runs for an instrument with a valid price_source.
_QUIET_NATIVE: ContextVar[bool] = ContextVar("alternate_listing_quiet_native", default=False)

# Provider loggers whose "no data" records are downgraded to INFO, and the
# lowest level downgraded for each. Stooq and Alpha Vantage WARNINGs report
# rate limits and cooldowns that affect every ticker, so only their per-ticker
# ERRORs are downgraded.
_NATIVE_MISS_LOGGERS = {
    "yfinance": logging.WARNING,
    "yahoo_timeseries": logging.ERROR,
    "stooq_timeseries": logging.ERROR,
    "backend.timeseries.fetch_alphavantage_timeseries": logging.ERROR,
    "backend.timeseries.fetch_ft_timeseries": logging.WARNING,
}


class _NativeMissFilter(logging.Filter):
    """Logs a provider's ERROR/WARNING at INFO while :data:`_QUIET_NATIVE` is set."""

    def __init__(self, lowest: int):
        super().__init__()
        self.lowest = lowest

    def filter(self, record: logging.LogRecord) -> bool:
        if _QUIET_NATIVE.get() and self.lowest <= record.levelno < logging.CRITICAL:
            record.levelno, record.levelname = logging.INFO, logging.getLevelName(logging.INFO)
        return True


for _name, _lowest in _NATIVE_MISS_LOGGERS.items():
    # A logger's filters only see records created on it, so each provider
    # logger gets its own; they are inert unless _QUIET_NATIVE is set.
    logging.getLogger(_name).addFilter(_NativeMissFilter(_lowest))


@contextmanager
def _native_misses_at_info() -> Iterator[None]:
    token = _QUIET_NATIVE.set(True)
    try:
        yield
    finally:
        _QUIET_NATIVE.reset(token)


# ──────────────────────────────────────────────────────────────
# FX conversion
# ──────────────────────────────────────────────────────────────
def _load_fx(currency: str, start: date, end: date) -> pd.DataFrame:
    """Stored ``currency``->GBP rates (``Date``, ``Rate``); never fetches."""
    from backend.timeseries.cache import load_fx_history

    return load_fx_history(currency, start, end)


def _rates_on(days: pd.Series, currency: str, start: date, end: date) -> pd.Series:
    """GBP-per-unit rate for each of ``days``, carried forward at most ``FX_FFILL_DAYS``; NaN where unknown."""
    if currency == "GBP":
        return pd.Series(1.0, index=days.index)
    fx = _load_fx(currency, start - timedelta(days=FX_FFILL_DAYS), end)
    if fx.empty:
        return pd.Series(float("nan"), index=days.index)
    fx = fx[["Date", "Rate"]].copy()
    fx["Date"] = pd.to_datetime(fx["Date"]).astype("datetime64[ns]")
    fx["Rate"] = pd.to_numeric(fx["Rate"], errors="coerce")
    fx = fx.dropna(subset=["Rate"]).sort_values("Date")
    left = pd.DataFrame({"Date": days.astype("datetime64[ns]"), "_pos": range(len(days))}).sort_values("Date")
    joined = pd.merge_asof(
        left, fx, on="Date", direction="backward", tolerance=pd.Timedelta(days=FX_FFILL_DAYS)
    ).sort_values("_pos")
    return pd.Series(joined["Rate"].to_numpy(), index=days.index)


def convert_prices(prices: pd.DataFrame, *, from_ccy: str, to_ccy: str, source: str) -> pd.DataFrame:
    """``prices`` (``STANDARD_COLUMNS``) converted from ``from_ccy`` to ``to_ccy`` with stored FX.

    Rows whose date has no usable rate on either side are dropped. Prices are
    rounded to six significant figures and ``Source`` is set to ``source``.
    """
    if prices.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    out = prices.copy()
    days = pd.to_datetime(out["Date"])
    start, end = days.min().date(), days.max().date()
    factor = _rates_on(days, from_ccy, start, end) / _rates_on(days, to_ccy, start, end)
    missing = factor.isna() | ~(factor > 0)
    if missing.any():
        logger.warning(
            "Dropping %s %s row(s) with no %s/%s FX rate within %s days",
            sanitise_log_value(int(missing.sum())),
            sanitise_log_value(source),
            sanitise_log_value(from_ccy),
            sanitise_log_value(to_ccy),
            sanitise_log_value(FX_FFILL_DAYS),
        )
    keep = (~missing).to_numpy()
    out, factor = out.loc[keep].copy(), factor.loc[keep]
    for col in PRICE_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce") * factor
    round_price_columns(out)
    out["Source"] = source
    return out[STANDARD_COLUMNS].reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# Fetch
# ──────────────────────────────────────────────────────────────
def _log_ignored_actions(raw: pd.DataFrame, full_ticker: str) -> None:
    for column in ("Dividends", "Stock Splits"):
        if column not in raw.columns:
            continue
        count = int((pd.to_numeric(raw[column], errors="coerce").fillna(0) != 0).sum())
        if count:
            logger.warning(
                "Ignoring %s %s on alternate listing %s: they are not stored for the instrument",
                sanitise_log_value(count),
                sanitise_log_value(column.lower()),
                sanitise_log_value(full_ticker),
            )


def fetch_alternate_listing(source: PriceSource, start: date, end: date) -> pd.DataFrame:
    """Traded daily prices of the alternate listing in its own currency (``STANDARD_COLUMNS``).

    Empty when Yahoo has no rows. Raises ``ValueError`` when Yahoo reports a
    currency other than ``source.currency``.
    """
    full_ticker = _build_full_ticker(source.ticker, source.exchange)
    stock = yf.Ticker(full_ticker)
    raw = stock.history(start=start, end=end + timedelta(days=1), interval="1d", **YAHOO_HISTORY_KWARGS)
    if raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    reported = _history_currency(stock)
    if reported is not None and reported != source.currency:
        raise ValueError(f"{full_ticker} is quoted in {reported}, not the declared {source.currency}")
    _log_ignored_actions(raw, full_ticker)
    return normalize_history(raw, full_ticker, "Yahoo")


# ──────────────────────────────────────────────────────────────
# Merge
# ──────────────────────────────────────────────────────────────
def _by_date(df: pd.DataFrame) -> pd.DataFrame:
    """``df`` with a normalised ``Date`` index, one row per date (the last)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS).set_index("Date")
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
    return out.drop_duplicates(subset="Date", keep="last").set_index("Date").sort_index()


def _native_reference(native: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """Stored native rows overlaid by freshly fetched ones; earlier converted rows are excluded."""
    stored_native = _by_date(stored)
    if not stored_native.empty and "Source" in stored_native.columns:
        labels = stored_native["Source"].astype("string").fillna("")
        stored_native = stored_native.loc[~labels.map(is_alternate_listing_source).astype(bool)]
    fresh = _by_date(native)
    if stored_native.empty:
        return fresh
    if fresh.empty:
        return stored_native
    return pd.concat([stored_native.loc[~stored_native.index.isin(fresh.index)], fresh]).sort_index()


def _traded(df: pd.DataFrame) -> pd.Series:
    """Per row of a date-indexed frame: a positive volume."""
    return pd.to_numeric(df["Volume"], errors="coerce").gt(0)


def _keep_native(reference: pd.DataFrame, conv: pd.DataFrame) -> pd.Index:
    """Dates where the native row beats ``conv`` (see the module docs for the rule)."""
    if reference.empty:
        return reference.index
    native_close = pd.to_numeric(reference["Close"], errors="coerce")
    has_close = native_close.gt(0)
    real = reference.index[(has_close & _traded(reference)).to_numpy()]
    untraded = reference.index[(has_close & ~_traded(reference)).to_numpy()]
    shared = untraded.intersection(conv.index)
    conv_close = pd.to_numeric(conv.loc[shared, "Close"], errors="coerce")
    agrees = (conv_close / native_close.loc[shared] - 1).abs().le(BASIS_TOLERANCE)
    better = shared[(agrees & _traded(conv.loc[shared])).to_numpy()]
    return real.union(untraded.difference(better))


def _closes(df: pd.DataFrame) -> pd.DataFrame:
    """Rows of a date-indexed frame with a positive close, as a ``Date`` column frame."""
    if df.empty:
        return df.reset_index()
    return df.loc[pd.to_numeric(df["Close"], errors="coerce").gt(0).to_numpy()].reset_index()


def _basis_references(reference: pd.DataFrame, stored: pd.DataFrame) -> list[pd.DataFrame]:
    """Series to check converted closes against, best first.

    Traded-basis native rows come first: ``same_basis`` holds a dividend-adjusted
    source (Stooq) to 0.5% on every date, tighter than the usual spread between
    two venues' closes. Then all native rows, then the stored window including
    earlier converted rows, so a refresh whose window has no native close is
    still checked for continuity.
    """
    labels = reference["Source"].astype("string").fillna("") if "Source" in reference.columns else None
    traded = reference if labels is None else reference.loc[~labels.isin(DIVIDEND_ADJUSTED_SOURCES).to_numpy()]
    return [_closes(traded), _closes(reference), _closes(_by_date(stored))]


def _basis_ok(reference: pd.DataFrame, stored: pd.DataFrame, converted: pd.DataFrame, label: str) -> bool:
    """Whether ``converted`` is on the native basis, judged on the first reference sharing a date."""
    conv_dates = set(_closes(_by_date(converted))["Date"])
    for candidate in _basis_references(reference, stored):
        if candidate.empty or not conv_dates & set(candidate["Date"]):
            continue
        if same_basis(candidate, converted):
            return True
        logger.warning(
            "Not using alternate listing for %s: converted closes do not match the stored series (ratio %s)",
            sanitise_log_value(label),
            sanitise_log_value(basis_ratio(candidate, converted)),
        )
        return False
    logger.info(
        "No stored close for %s shares a date with its alternate listing; trusting the declared listing",
        sanitise_log_value(label),
    )
    return True


def overlay_alternate_listing(
    native: pd.DataFrame, stored: pd.DataFrame, converted: pd.DataFrame, *, label: str
) -> pd.DataFrame:
    """Freshly fetched ``native`` rows with ``converted`` rows filling what native lacks.

    See the module docs for the per-date rule. ``stored`` is the cached series
    for the instrument; its rows are consulted but not returned, so a stored
    native row with a real close stays as it is.
    """
    if converted.empty:
        return native
    merged = _overlay_if_same_basis(native, stored, converted, label)
    return native if merged is None else merged


def _overlay_if_same_basis(
    native: pd.DataFrame, stored: pd.DataFrame, converted: pd.DataFrame, label: str
) -> pd.DataFrame | None:
    """:func:`overlay_alternate_listing` for a non-empty ``converted``; ``None`` when its basis is refused."""
    reference = _native_reference(native, stored)
    if not _basis_ok(reference, stored, converted, label):
        return None
    conv = _closes(_by_date(converted)).set_index("Date")
    conv = conv.loc[~conv.index.isin(_keep_native(reference, conv))]
    fresh = _by_date(native)
    fresh = fresh.loc[~fresh.index.isin(conv.index)]
    combined = pd.concat([fresh, conv]).sort_index().reset_index()
    if not conv.empty:
        logger.info(
            "Filled %s date(s) for %s from %s",
            sanitise_log_value(len(conv)),
            sanitise_log_value(label),
            sanitise_log_value(conv["Source"].iloc[0]),
        )
    return combined[STANDARD_COLUMNS]


def _stored_series(ticker: str, exchange: str) -> pd.DataFrame:
    from backend.timeseries.cache import load_cached_meta_timeseries_full

    return load_cached_meta_timeseries_full(ticker, exchange)


def _window(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    days = pd.to_datetime(df["Date"]).dt.date
    return df.loc[((days >= start) & (days <= end)).to_numpy()]


NativeFetch = Callable[[date, date], pd.DataFrame]


def _converted_listing(source: PriceSource, target: str, label: str, start: date, end: date) -> pd.DataFrame:
    """The alternate listing's prices in ``target``, labelled as the instrument's own series."""
    converted = convert_prices(
        fetch_alternate_listing(source, start, end),
        from_ccy=source.currency,
        to_ccy=target,
        source=alternate_listing_source(source.full_ticker, target),
    )
    # Stored as the instrument's own series; ``Source`` records the listing.
    converted["Ticker"] = label
    return converted


def _log_failure(label: str, exc: Exception) -> None:
    logger.warning(
        "Alternate listing price source failed for %s: %s", sanitise_log_value(label), sanitise_log_value(exc)
    )


def _uncovered_weekdays(start: date, end: date, converted: pd.DataFrame, stored: pd.DataFrame) -> list[date]:
    """Weekdays in the window with a close in neither ``converted`` nor ``stored``."""
    covered = set(_closes(_by_date(converted))["Date"]) | set(_closes(_by_date(stored))["Date"])
    return [day.date() for day in pd.bdate_range(start, end) if day not in covered]


def _fill_gaps(
    fetch_native: NativeFetch, source: PriceSource, target: str, ticker: str, exchange: str, start: date, end: date
) -> pd.DataFrame:
    """The native chain over the whole window, then the converted listing where it lacks a close."""
    label = f"{ticker}.{exchange}"
    with _native_misses_at_info():
        native = fetch_native(start, end)
    if native.empty:
        logger.info(
            "No native prices for %s; using alternate listing %s",
            sanitise_log_value(label),
            sanitise_log_value(source.full_ticker),
        )
    try:
        converted = _converted_listing(source, target, label, start, end)
        stored = _window(_stored_series(ticker, exchange), start, end)
    except Exception as exc:
        _log_failure(label, exc)
        return native
    return overlay_alternate_listing(native, stored, converted, label=label)


def _alternate_first(
    fetch_native: NativeFetch, source: PriceSource, target: str, ticker: str, exchange: str, start: date, end: date
) -> pd.DataFrame:
    """The converted listing first; the native chain only over weekdays it and the store leave uncovered."""
    label = f"{ticker}.{exchange}"
    try:
        converted = _converted_listing(source, target, label, start, end)
        stored = _window(_stored_series(ticker, exchange), start, end)
    except Exception as exc:
        _log_failure(label, exc)
        return fetch_native(start, end)
    uncovered = _uncovered_weekdays(start, end, converted, stored)
    if uncovered:
        logger.info(
            "Alternate listing %s leaves %s weekday(s) of %s uncovered between %s and %s; trying native providers",
            sanitise_log_value(source.full_ticker),
            sanitise_log_value(len(uncovered)),
            sanitise_log_value(label),
            sanitise_log_value(uncovered[0]),
            sanitise_log_value(uncovered[-1]),
        )
        with _native_misses_at_info():
            native = fetch_native(uncovered[0], uncovered[-1])
    else:
        logger.debug(
            "Alternate listing %s covers %s from %s to %s; skipping native providers",
            sanitise_log_value(source.full_ticker),
            sanitise_log_value(label),
            sanitise_log_value(start),
            sanitise_log_value(end),
        )
        native = pd.DataFrame(columns=STANDARD_COLUMNS)
    if converted.empty:
        return native
    merged = _overlay_if_same_basis(native, stored, converted, label)
    if merged is None:
        # Refused as a whole: the native chain is all there is, for every date.
        return fetch_native(start, end)
    return merged


def _price_source_for(label: str) -> tuple[PriceSource, str] | None:
    """The instrument's parsed ``price_source`` and currency, or ``None`` when absent or invalid (logged)."""
    meta = get_instrument_meta(label)
    if not meta or meta.get("price_source") is None:
        return None
    try:
        source = parse_price_source(meta, own=label)
    except ValueError as exc:
        _log_failure(label, exc)
        return None
    if source is None:
        return None
    return source, str(meta["currency"]).strip()


def fetch_with_price_source(
    fetch_native: NativeFetch, ticker: str, exchange: str, start: date, end: date
) -> pd.DataFrame:
    """Prices for ``ticker.exchange``: ``fetch_native(start, end)`` combined with its ``price_source``.

    ``fetch_native`` runs the instrument's own provider chain for a date range.
    Without a valid ``price_source`` it is called once for the whole window and
    its result returned as is. Otherwise the block's ``mode`` sets the fetch
    order (see the module docs).
    """
    resolved = _price_source_for(f"{ticker}.{exchange}")
    if resolved is None:
        return fetch_native(start, end)
    source, target = resolved
    order = _alternate_first if source.mode == MODE_PRIMARY else _fill_gaps
    return order(fetch_native, source, target, ticker, exchange, start, end)


def apply_price_source(native: pd.DataFrame, ticker: str, exchange: str, start: date, end: date) -> pd.DataFrame:
    """``native`` merged with the instrument's ``price_source`` listing, or unchanged without one.

    This is the ``fill_gaps`` merge for an already fetched ``native`` frame,
    whatever the block's ``mode``. Any failure (invalid block, fetch error,
    currency mismatch) is logged and leaves ``native`` as it was.
    """
    label = f"{ticker}.{exchange}"
    resolved = _price_source_for(label)
    if resolved is None:
        return native
    source, target = resolved
    try:
        converted = _converted_listing(source, target, label, start, end)
        stored = _window(_stored_series(ticker, exchange), start, end)
    except Exception as exc:
        _log_failure(label, exc)
        return native
    return overlay_alternate_listing(native, stored, converted, label=label)
