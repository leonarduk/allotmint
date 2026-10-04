from __future__ import annotations

import datetime as dt
import inspect
import logging
import threading
from collections import OrderedDict
from datetime import timedelta
from typing import Any, Dict, Optional

import pandas as pd
import requests

from backend.common import refresh_progress
from backend.common.approvals import is_approval_valid
from backend.common.constants import (
    ACQUIRED_DATE,
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
    TICKER,
    UNITS,
)
from backend.common.currency import CurrencyNormaliser
from backend.common.instruments import get_instrument_meta
from backend.common.numeric_utils import is_nan
from backend.common.sector_labels import (
    CASH_SECTOR_LABEL,
    is_cash_instrument,
    normalise_optional_region,
    normalise_optional_sector,
)
from backend.common.ticker_utils import canonical_ticker
from backend.common.user_config import UserConfig
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import (
    is_cache_only,
    load_meta_timeseries_range,
    register_meta_cache_clearer,
)
from backend.utils.pricing_dates import PricingDateCalculator
from backend.utils.timeseries_helpers import (
    _nearest_weekday,
    apply_scaling,
    get_scaling_override,
)

logger = logging.getLogger(__name__)


# ───────────── helpers ─────────────
def _fx_to_base(from_ccy: str, to_ccy: str, cache: Dict[str, float]) -> float:
    """Resolve FX via portfolio_utils lazily to avoid import cycles."""
    from backend.common import portfolio_utils

    return portfolio_utils._fx_to_base(from_ccy, to_ccy, cache)


def _parse_date(val) -> Optional[dt.date]:
    # pd.NaT subclasses datetime and NaT.date() is NaT, which compares False
    # with any date -- so a missing row date would read as fresh (#8595).
    if val is None or val is pd.NaT:
        return None
    if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
        return val
    if isinstance(val, dt.datetime):
        return val.date()
    try:
        return dt.datetime.fromisoformat(str(val)).date()
    except ValueError:
        return None


def _lower_name_map(df: pd.DataFrame) -> Dict[str, str]:
    return {c.lower(): c for c in df.columns}


def _is_pence_currency(raw: str) -> bool:
    """Backwards-compatible wrapper for pence currency checks."""
    return CurrencyNormaliser.from_raw(raw).is_pence


def load_latest_prices(full_tickers: list[str], *, report_progress: bool = False) -> dict[str, float]:
    """Return latest close prices in GBP for each requested ticker.

    Thin wrapper over :func:`load_latest_closes` that drops the close dates;
    see that function for the full contract.
    """
    closes = load_latest_closes(full_tickers, report_progress=report_progress)
    return {key: price for key, (price, _close_date) in closes.items()}


def load_latest_closes(
    full_tickers: list[str], *, report_progress: bool = False
) -> dict[str, tuple[float, Optional[dt.date]]]:
    """Return ``(close_gbp, close_date)`` for each requested ticker.

    ``close_date`` is the date of the row the close was read from (``None``
    when the feed's date column can't be parsed). Callers use it to judge
    staleness against the latest completed trading day (#8595) instead of
    assuming every last close is stale.

    Contract:
    - Output values are always GBP-normalised regardless of source columns.
    - If ``Close_gbp``/``close_gbp`` exists, use it directly.
    - Otherwise use native close and convert to GBP using instrument metadata
      and scaling:
      - If ``get_scaling_override`` already applied pence scaling to the
        DataFrame/quote (scale == 0.01, the pence_factor), no additional
        pence conversion is applied.
      - Otherwise, native values are converted through ``CurrencyNormaliser``
        (pence-to-GBP and non-GBP FX paths).

    Additional behaviour:
    - Uses end_date = yesterday via PricingDateCalculator
    - Accepts 'HFEL.L' or 'HFEL' (defaults exchange 'L')
    - Skips empties instead of returning 0.00

    ``report_progress`` opts this call into ``refresh_progress`` reporting;
    leave it off (the default) for any caller that isn't the user-triggered
    refresh job, so this ticker list can never overwrite the refresh job's
    progress display with an unrelated one (see
    :mod:`backend.common.refresh_progress`).
    """
    result: dict[str, tuple[float, Optional[dt.date]]] = {}
    if not full_tickers:
        return result

    calc = PricingDateCalculator()
    start_date, end_date = calc.lookback_range(365)

    from backend.common import instrument_api

    fx_cache: Dict[str, float] = {}
    unpriced: list[str] = []

    for i, full in enumerate(full_tickers):
        priced_before = len(result)
        resolved = instrument_api._resolve_full_ticker(full, result)
        if resolved:
            ticker, exchange = resolved
        else:
            ticker = full.split(".", 1)[0]
            exchange = "L"
            logger.debug("Could not resolve exchange for %s; defaulting to L", full)

        try:
            df = load_meta_timeseries_range(
                ticker=ticker,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                continue

            scale = get_scaling_override(ticker, exchange, None)
            df = apply_scaling(df, scale)

            name_map = _lower_name_map(df)
            close_gbp_col = name_map.get("close_gbp")
            close_native_col = name_map.get("close") or name_map.get("adj close") or name_map.get("adj_close")

            if not close_gbp_col and not close_native_col:
                continue

            # Sort by, and read the close date from, the named "Date" column. The
            # timeseries cache guarantees it (EXPECTED_COLS in
            # backend/timeseries/cache.py). An ad-hoc frame without one keeps its
            # own row order -- sorting by some other column (e.g. the price)
            # would pick the wrong row -- and has no close date, i.e. stale.
            date_col = name_map.get("date")
            if date_col is None:
                logger.warning(
                    "no Date column for %s; using last row in feed order, close date unknown",
                    sanitise_log_value(full),
                )
            else:
                df = df.sort_values(date_col)
            last = df.iloc[-1]

            selected_col = close_gbp_col or close_native_col
            val = float(last[selected_col])

            if not (val == val and val != float("inf") and val != float("-inf")):
                continue

            if close_gbp_col is None:
                full_ticker = f"{ticker}.{exchange}"
                meta = (
                    get_instrument_meta(full_ticker) or get_instrument_meta(full) or get_instrument_meta(ticker) or {}
                )

                raw_currency = str(meta.get("currency") or "").strip()
                if not raw_currency:
                    continue
                normaliser = CurrencyNormaliser.from_raw(raw_currency)

                # Skip pence->GBP conversion only when apply_scaling already applied the
                # pence factor (scale == 0.01). A non-zero, non-pence-factor scale (e.g.
                # 0.5 for a data-provider quirk) does NOT imply pence conversion happened.
                pence_scaled_in_dataframe = normaliser.is_pence and scale == normaliser.pence_factor
                if not pence_scaled_in_dataframe:
                    try:
                        val = normaliser.to_gbp(val, fx_cache, _fx_to_base)
                    except ValueError:
                        continue

            if not pd.notna(val) or val <= 0:
                continue

            key = f"{ticker}.{exchange}"
            result[key] = (val, _parse_date(last[date_col]) if date_col is not None else None)

        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            logger.warning(
                "latest price fetch failed for %s: %s",
                sanitise_log_value(full),
                sanitise_log_value(e),
            )
        finally:
            if len(result) == priced_before:
                unpriced.append(full)
            if report_progress:
                refresh_progress.update(full, i + 1)

    logger.info("Latest prices fetched: %d/%d", len(result), len(full_tickers))
    if unpriced:
        # Name the symbols so a refresh that keeps failing for one ticker is
        # visible in the logs rather than only as a shortfall in the count (#8599).
        logger.warning(
            "No latest price for %s ticker(s): %s",
            sanitise_log_value(len(unpriced)),
            sanitise_log_value(", ".join(unpriced)),
        )
    return result


def load_live_prices(full_tickers: list[str]) -> dict[str, Dict[str, object]]:
    """Fetch real-time quotes for ``full_tickers``.

    Returns a mapping ``{'TICKER': {'price': float, 'timestamp': datetime}}``
    where the timestamp is timezone-aware (UTC). Entries with missing data are
    skipped. Any network or parsing errors result in an empty mapping.
    """

    out: dict[str, Dict[str, object]] = {}
    if not full_tickers:
        return out

    symbols = ",".join(full_tickers)
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"

    try:
        fx_cache: Dict[str, float] = {}
        resp = requests.get(url, timeout=5)
        raise_for_status = getattr(resp, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        payload = resp.json().get("quoteResponse", {}).get("result", [])

        for row in payload:
            sym = row.get("symbol")
            price = row.get("regularMarketPrice")
            ts = row.get("regularMarketTime")
            if not sym or price is None or ts is None:
                continue

            price = float(price)

            # Apply scaling override first.
            tkr, exch = (sym.split(".", 1) + [""])[:2]
            scale = get_scaling_override(tkr, exch, None)
            price *= scale

            # Enforce GBP output contract without double-converting pence instruments.
            meta = get_instrument_meta(sym) or get_instrument_meta(tkr) or {}
            raw_currency = str(meta.get("currency") or "GBP").strip()
            normaliser = CurrencyNormaliser.from_raw(raw_currency)

            # Skip pence->GBP conversion only when apply_scaling already applied the
            # pence factor (scale == 0.01). A non-zero, non-pence-factor scale (e.g.
            # 0.5 for a data-provider quirk) does NOT imply pence conversion happened.
            pence_scaled_in_quote = normaliser.is_pence and scale == normaliser.pence_factor
            if not pence_scaled_in_quote:
                try:
                    price = normaliser.to_gbp(price, fx_cache, _fx_to_base)
                except ValueError:
                    continue

            if not pd.notna(price) or price <= 0:
                continue

            out[sym.upper()] = {
                "price": price,
                "timestamp": dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc),
            }
    except Exception as exc:
        logger.warning(
            "live price fetch failed for %s: %s",
            sanitise_log_value(symbols),
            sanitise_log_value(exc),
        )

    return out


# In-memory map populated elsewhere; exported for consumers that rely on it.
latest_prices: Dict[str, float] = {}


def _close_column(df: pd.DataFrame) -> Optional[str]:
    """
    Prefer GBP close if present, else fall back to Close or Adj Close,
    case-insensitive.
    """
    nm = _lower_name_map(df)
    return nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")


# ─────── cost basis (single source of truth) ───────
def _derived_cost_basis_close_px(
    ticker: str,
    exchange: str,
    acq: dt.date,
    cache: dict[str, float],
) -> Optional[float]:
    """
    Find a scaled close price near acquisition date (±2 weekdays). Cached by key.
    """
    start = _nearest_weekday(acq - dt.timedelta(days=2), False)
    end = _nearest_weekday(acq + dt.timedelta(days=2), True)
    key = f"{ticker}.{exchange}_{acq}"
    if key in cache:
        return cache[key]

    df = load_meta_timeseries_range(ticker, exchange, start_date=start, end_date=end)
    if df is None or df.empty:
        return None

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    col = _close_column(df)
    if not col or df[col].empty:
        return None

    px = float(df[col].iloc[0])
    if is_nan(px):
        return None
    cache[key] = px
    return px


# apply_scaling (backend/utils/timeseries_helpers.py) only multiplies columns
# whose lowercase name is exactly one of these -- notably *not* "close_gbp",
# "adj close" or "adj_close". A GBP-converted or adjusted close was therefore
# never scaled even before this refactor; only the raw OHLC columns were.
_SCALABLE_COLUMNS = {"open", "high", "low", "close"}


def _load_unscaled_price_for_date_impl(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close_gbp",
) -> tuple[Optional[float], Optional[str], bool, Optional[dt.date]]:
    """Load a single-day DF and return the requested field's *unscaled* value,
    its source, whether that value is subject to scaling, and the date of the
    row actually served. For close prices we prefer the GBP-converted column
    when available, falling back to the regular close.

    ``load_meta_timeseries_range`` walks back up to four days when ``d`` has
    no row, so the row date can be earlier than ``d``; ``enrich_holding``
    compares it with the reporting date to decide staleness (#7919).

    Deliberately does not apply ``get_scaling_override``/``apply_scaling`` --
    see ``_load_unscaled_price_for_date_cache_only`` for why (#8232 review).
    The caller applies ``scale`` itself, but only when the third element here
    is ``True``: replicating ``apply_scaling``'s behavior exactly requires
    knowing which physical column the value came from, since ``apply_scaling``
    skips ``close_gbp``/``adj close``/``adj_close`` (#8232 review round 2 --
    the original ``price * scale`` deferral applied to *every* column,
    silently re-scaling an already-GBP-converted price).

    Also short-circuits ``CASH`` tickers the same way ``_get_price_for_date_scaled``
    does, rather than relying on its caller to: this function is called
    directly by ``scripts/profile_single_day_lookups.py`` and by tests, and a
    ``CASH`` ticker has no backing parquet to hit ``load_meta_timeseries_range``
    for (#8232 review round 4).
    """
    if "CASH" in ticker.upper().split("."):
        return 1.0, None, False, d

    df = load_meta_timeseries_range(ticker=ticker, exchange=exchange, start_date=d, end_date=d)
    if df is None or df.empty:
        return None, None, False, None

    nm = _lower_name_map(df)
    col = None
    if field.lower() in {"close", "close_gbp"}:
        col = nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")
    else:
        col = nm.get(field.lower())
    if not col:
        return None, None, False, None

    try:
        price = float(df.iloc[0][col])
    except (ValueError, TypeError, KeyError, IndexError):
        return None, None, False, None

    if is_nan(price):
        return None, None, False, None

    src = df.iloc[0].get("Source")
    if is_nan(src):
        src = None
    return price, src, col.lower() in _SCALABLE_COLUMNS, _parse_date(df.iloc[0].get("Date"))


_UNSCALED_PRICE_CACHE_MAXSIZE = 2048
# (price, source, scalable, row_date) -- see _load_unscaled_price_for_date_impl.
_UnscaledPrice = tuple[float, Optional[str], bool, Optional[dt.date]]
_unscaled_price_cache: "OrderedDict[tuple[str, str, dt.date, str], _UnscaledPrice]" = OrderedDict()
# Guards _unscaled_price_cache's mutations only, not the load_meta_timeseries_range
# call on a miss -- see instrument_api._close_on_cache_lock's identical comment
# (#8232 review round 5): OrderedDict.move_to_end/popitem aren't atomic across
# a read-modify-write sequence the way lru_cache's C implementation is, and
# FastAPI runs sync endpoints in a threadpool.
_unscaled_price_cache_lock = threading.Lock()


def _load_unscaled_price_for_date_cache_only(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close_gbp",
) -> tuple[Optional[float], Optional[str], bool, Optional[dt.date]]:
    """Memoized, *unscaled* body of ``_get_price_for_date_scaled``, used only
    inside a ``cache_only()`` block (#8211).

    ``enrich_holding`` -> ``get_effective_cost_basis_gbp`` calls this up to
    several times per holding, and each call otherwise pays the full
    ``load_meta_timeseries_range`` round trip (the per-(ticker,range) LRU,
    ``apply_date_range``, ``_ensure_schema``, and an uncached FX merge in
    ``_convert_to_base_currency``) for what is conceptually one row. Only
    memoized for cache-only reads (page requests): a live/background-refresh
    read is specifically asking for fresh data, which this process-lifetime
    cache must not intercept. Registered with
    ``backend.timeseries.cache.register_meta_cache_clearer`` so a stale
    underlying file still invalidates this cache the same way it invalidates
    the timeseries module's own.

    Memoizes only the *unscaled* price (plus whether it's scalable at all --
    see ``_load_unscaled_price_for_date_impl``), with ``get_scaling_override``
    and the scaling multiply applied fresh on every call in
    ``_get_price_for_date_scaled`` instead of being baked into this cache:
    ``get_scaling_override`` reads ``data/scaling_overrides.json`` fresh every
    call with no caching of its own, so memoizing its already-applied result
    here would risk serving a stale scaled price if that file changes while
    this process is running (#8232 review).

    A missing result (``None``, i.e. no cached row for this day) is
    deliberately not memoized either, for the same reason ``_close_on_cache_only``
    (backend/common/instrument_api.py) doesn't: ``load_meta_timeseries_range``
    queues the ticker on ``refresh_queue`` when cache-only reads find nothing,
    and caching the ``None`` here would silently suppress that queueing for the
    rest of this process's lifetime, including once real data finally lands.
    """
    key = (ticker, exchange, d, field)
    with _unscaled_price_cache_lock:
        if key in _unscaled_price_cache:
            _unscaled_price_cache.move_to_end(key)
            return _unscaled_price_cache[key]
    result = _load_unscaled_price_for_date_impl(ticker, exchange, d, field)
    if result[0] is not None:
        with _unscaled_price_cache_lock:
            _unscaled_price_cache[key] = result
            _unscaled_price_cache.move_to_end(key)
            if len(_unscaled_price_cache) > _UNSCALED_PRICE_CACHE_MAXSIZE:
                _unscaled_price_cache.popitem(last=False)
    return result


def _clear_unscaled_price_cache() -> None:
    with _unscaled_price_cache_lock:
        _unscaled_price_cache.clear()


_load_unscaled_price_for_date_cache_only.cache_clear = _clear_unscaled_price_cache  # type: ignore[attr-defined]


def _get_price_for_date_scaled(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close_gbp",
) -> tuple[Optional[float], Optional[str]]:
    price, src, _row_date = _get_dated_price_for_date_scaled(ticker, exchange, d, field)
    return price, src


def _get_dated_price_for_date_scaled(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close_gbp",
) -> tuple[Optional[float], Optional[str], Optional[dt.date]]:
    """Like :func:`_get_price_for_date_scaled`, plus the date of the row used
    (which may be earlier than ``d`` -- see ``_load_unscaled_price_for_date_impl``)."""
    parts = ticker.upper().split(".")
    if "CASH" in parts:
        # Also duplicated in _load_unscaled_price_for_date_impl for direct
        # callers -- load-bearing here too: removing it would route CASH
        # through _load_unscaled_price_for_date_cache_only and memoize it
        # under a key with no backing file for invalidation to bust (#8232
        # review round 5).
        return 1.0, None, d

    if is_cache_only():
        price, src, scalable, row_date = _load_unscaled_price_for_date_cache_only(ticker, exchange, d, field)
    else:
        price, src, scalable, row_date = _load_unscaled_price_for_date_impl(ticker, exchange, d, field)
    if price is None:
        return None, None, None
    if not scalable:
        return price, src, row_date

    scale = get_scaling_override(ticker, exchange, None)
    if scale is not None and scale != 1:
        price = price * scale
    return price, src, row_date


def _snapshot_is_stale(snap: Dict[str, Any], reporting_date: dt.date) -> bool:
    """Staleness of a price snapshot entry relative to ``reporting_date`` (#7919).

    Stale when the entry says so (live quotes older than 15 minutes, set in
    ``backend/common/prices.py``) *or* its ``last_price_date`` is before the
    reporting date. The timeseries-built snapshot
    (``portfolio_utils.refresh_snapshot_in_memory_from_timeseries``) carries
    only ``last_price_date``; an entry with neither field is treated as stale
    rather than silently fresh.
    """
    flag = snap.get("is_stale")
    price_date = _parse_date(snap.get("last_price_date"))
    if flag is True:
        return True
    if price_date is not None:
        return price_date < reporting_date
    return flag is None


register_meta_cache_clearer(_load_unscaled_price_for_date_cache_only.cache_clear)


def get_effective_cost_basis_gbp(
    h: Dict[str, Any],
    price_cache: dict[str, float],
    price_hint: float | None = None,
) -> float:
    """
    If booked cost exists, use it. Otherwise derive:
      units * (close near acquisition OR latest cache price OR current price).
    """
    units = float(h.get(UNITS) or 0.0)
    if units <= 0:
        return 0.0

    from backend.common import instrument_api

    full = (h.get(TICKER) or "").upper()
    ticker = full.split(".", 1)[0]
    resolved = instrument_api._resolve_full_ticker(full, price_cache)
    if resolved:
        ticker, exchange = resolved
    else:
        exchange = "L"
        logger.debug("Could not resolve exchange for %s; defaulting to L", full)

    scale = get_scaling_override(ticker, exchange, None)
    booked_raw = h.get(COST_BASIS_GBP)
    try:
        booked_total = float(booked_raw) if booked_raw is not None else 0.0
    except (TypeError, ValueError):
        booked_total = 0.0

    if booked_total > 0:
        unscaled_total = round(booked_total, 2)
        scaled_total = None
        if scale not in (None, 0, 1):
            scaled_total = round(booked_total * scale, 2)

        chosen_total = unscaled_total
        if scaled_total is not None:
            if price_hint is not None and units > 0:
                expected_total = round(units * price_hint, 2)
                if abs(scaled_total - expected_total) < abs(unscaled_total - expected_total):
                    chosen_total = scaled_total
            else:
                chosen_total = scaled_total

        h[COST_BASIS_GBP] = chosen_total
        return chosen_total

    acq = _parse_date(h.get(ACQUIRED_DATE))

    close_px = None
    if acq:
        close_px = _derived_cost_basis_close_px(ticker, exchange, acq, price_cache)
    if close_px is None:
        close_px = price_cache.get(full)
    if close_px is None:
        # No acquisition date on record (#7220) and no cached historical
        # price: fall back to the current price rather than a fabricated
        # date. This intentionally reports cost == market value (no
        # gain/loss) instead of leaving cost at 0, which would otherwise
        # invent a large, misleading "unrealised gain" equal to the entire
        # market value.
        #
        # This value is still a guess, not a fact, so it must not be
        # reported as "derived" (a real historical-price derivation) --
        # tag it distinctly so callers/UI can tell the two apart and avoid
        # presenting the resulting break-even gain as a confident £0.00
        # (review follow-up on #7220).
        close_px = price_hint
        if close_px is not None:
            h["cost_basis_source"] = "unknown"

    if close_px is None:
        return 0.0

    return round(units * float(close_px), 2)


# ─────── booked cost plausibility (#8472) ───────
# A booked cost whose implied unit cost (book / units) is more than this factor
# below or above the reference price is treated as suspect (e.g. an unscaled
# pence figure or a partial book cost from the source statement). Downstream
# reports call this "cost_basis_suspect" (#8596). It usually means the *price*
# is wrong, not the cost: a pence close read as pounds because the ticker has
# no pence entry in data/scaling_overrides.json or doesn't resolve to "L".
BOOK_COST_PLAUSIBILITY_BAND = 20.0
BOOK_COST_SUSPECT_SOURCE = "book_suspect"
BOOK_COST_OUT_OF_BAND_WARNING = "implied_unit_cost_out_of_band"
# cost_basis_source values whose cost (and therefore gain) must not be presented
# or aggregated as fact: a guessed cost (#7220) or an implausible booked cost.
# Keep in sync with UNRELIABLE_SOURCES in frontend/src/lib/costBasis.ts (both
# sides have a test pinning the contents: tests/test_holding_utils_price_cost_basis.py
# and frontend/tests/unit/lib/costBasis.test.ts).
COST_BASIS_UNRELIABLE_SOURCES = frozenset({"unknown", BOOK_COST_SUSPECT_SOURCE})
# (ticker, exchange) pairs whose acquisition-close lookup failure was already
# logged at WARNING; later failures for the same pair log at DEBUG.
_ACQ_CLOSE_FAILURE_WARNED: set[tuple[str, str]] = set()


def is_cost_basis_unreliable(source: object) -> bool:
    """True when ``cost_basis_source`` marks the cost as a guess or suspect."""
    return source in COST_BASIS_UNRELIABLE_SOURCES


def _book_cost_reference_price(
    ticker: str,
    exchange: str,
    acq: Optional[dt.date],
    current_price: Optional[float],
    price_cache: dict[str, float],
) -> Optional[float]:
    """Acquisition-date close when known and available, else the current price.

    The acquisition-date close is preferred so a genuine long-held multi-bagger
    is judged against what it actually cost at the time, not today's price.
    """
    if acq is not None:
        try:
            acq_px = _derived_cost_basis_close_px(ticker, exchange, acq, price_cache)
        except Exception as exc:  # noqa: BLE001 -- see justification below
            # load_meta_timeseries_range can raise arbitrary errors from the
            # cache/fetch layer (ValueError in offline mode with no cache,
            # network/HTTP errors from live fetchers, parquet/pyarrow read
            # errors). This lookup only refines a plausibility *flag*, so any
            # failure falls back to the current price (logged, not swallowed)
            # instead of failing enrichment of the whole booked holding.
            # WARNING once per ticker per process, DEBUG thereafter, so an
            # offline run doesn't flood the log on every page load.
            key = (ticker, exchange)
            log = logger.debug if key in _ACQ_CLOSE_FAILURE_WARNED else logger.warning
            _ACQ_CLOSE_FAILURE_WARNED.add(key)
            log(
                "acquisition close unavailable for %s.%s on %s: %s",
                sanitise_log_value(ticker),
                sanitise_log_value(exchange),
                sanitise_log_value(acq),
                sanitise_log_value(exc),
            )
            acq_px = None
        if acq_px is not None and acq_px > 0:
            return float(acq_px)
    if current_price is not None and not is_nan(current_price) and current_price > 0:
        return float(current_price)
    return None


def _flag_implausible_book_cost(
    out: Dict[str, Any],
    units: float,
    ticker: str,
    exchange: str,
    acq: Optional[dt.date],
    current_price: Optional[float],
    price_cache: dict[str, float],
) -> None:
    """Flag (never replace) a booked cost whose implied unit cost is out of band.

    Read-time only: the booked ``cost_basis_gbp`` is left untouched, but the
    holding is tagged ``book_suspect`` with a ``cost_basis_warning`` and its
    gain fields are nulled so an absurd gain is not presented as fact.
    """
    if out.get("cost_basis_source") != "book" or units <= 0:
        return
    try:
        book = float(out.get(COST_BASIS_GBP) or 0.0)
    except (TypeError, ValueError):
        book = 0.0
    if not book > 0:  # also rejects NaN
        return
    reference = _book_cost_reference_price(ticker, exchange, acq, current_price, price_cache)
    if reference is None:
        return
    implied = book / units
    band = BOOK_COST_PLAUSIBILITY_BAND
    if reference / band <= implied <= reference * band:
        return
    logger.info(
        "Booked cost for %s looks implausible: implied unit cost %s vs reference %s",
        sanitise_log_value(out.get(TICKER)),
        sanitise_log_value(f"{implied:.4f}"),
        sanitise_log_value(f"{reference:.4f}"),
    )
    out["cost_basis_source"] = BOOK_COST_SUSPECT_SOURCE
    out["cost_basis_warning"] = BOOK_COST_OUT_OF_BAND_WARNING
    for key in ("gain_gbp", "unrealised_gain_gbp", "unrealized_gain_gbp", "gain_pct"):
        out[key] = None


# ───────────── canonical enrichment ─────────────
def enrich_holding(
    h: Dict[str, Any],
    today: dt.date,
    price_cache: dict[str, float],
    approvals: dict[str, dt.date] | None = None,
    user_config: UserConfig | None = None,
    *,
    calc: PricingDateCalculator | None = None,
) -> Dict[str, Any]:
    """
    Canonical enrichment used by both owner and group builders.
    Produces the same keys in both paths.
    """
    out = dict(h)  # do not mutate caller
    # Canonical key so a padded LSE EPIC ("BP.") is priced and labelled as
    # "BP.L" -- the key the price snapshot and timeseries cache use (#8600).
    full = canonical_ticker(out.get(TICKER))
    if full:
        out[TICKER] = full
    meta = get_instrument_meta(full)
    ucfg = user_config or UserConfig(
        hold_days_min=config.hold_days_min,
        approval_exempt_types=config.approval_exempt_types,
        approval_exempt_tickers=config.approval_exempt_tickers,
    )

    account_ccy = (h.get("currency") or "GBP").upper()
    from backend.common.portfolio_utils import get_security_meta  # local import to avoid circular

    sec_meta = get_security_meta(full) or {}
    instr_meta = meta or {}
    # Instrument metadata should win over security metadata derived from portfolios.
    meta = {**sec_meta, **instr_meta}

    if _is_cash(full, account_ccy):
        units = float(out.get(UNITS, 0) or 0.0)
        out["name"] = out.get("name") or _cash_name(full, account_ccy)
        out["currency"] = meta.get("currency") or account_ccy
        out["instrument_type"] = meta.get("instrumentType") or meta.get("instrument_type") or "Cash"
        # Cash is labelled "Cash" in every sector view rather than left blank
        # (shown as "Unknown sector"/"Other"); see #8530.
        out["sector"] = CASH_SECTOR_LABEL
        out["region"] = normalise_optional_region(out.get("region") or meta.get("region"))

        out["price"] = 1.0
        out["current_price_gbp"] = 1.0 if account_ccy == "GBP" else None

        out["market_value_gbp"] = units if account_ccy == "GBP" else None
        out["gain_gbp"] = 0.0
        out["unrealised_gain_gbp"] = 0.0
        out["unrealized_gain_gbp"] = 0.0
        out["gain_pct"] = 0.0
        out["day_change_gbp"] = 0.0

        # Cash is priced 1:1 (see out["price"]/out["current_price_gbp"] above), so
        # cost basis must always equal market value regardless of any stored
        # cost_basis_gbp on the raw holding record. Previously this used
        # setdefault(), which let a stale/incorrect stored value (e.g. one
        # accidentally recorded in pence rather than pounds, see #7012) leak
        # straight through to the API response, producing a ~100x-too-low
        # cost basis and a phantom unrealised gain for cash positions.
        out[COST_BASIS_GBP] = out["market_value_gbp"]
        out[EFFECTIVE_COST_BASIS_GBP] = out[COST_BASIS_GBP]

        out["days_held"] = None
        out["sell_eligible"] = True
        out["eligible_on"] = None
        out["days_until_eligible"] = 0
        out["next_eligible_sell_date"] = None
        out["cost_basis_source"] = "cash"

        return out

    from backend.common import instrument_api

    ticker = full.split(".", 1)[0]
    resolved = instrument_api._resolve_full_ticker(full, price_cache)
    if resolved:
        ticker, exchange = resolved
    else:
        exchange = "L"
        logger.debug("Could not resolve exchange for %s; defaulting to L", sanitise_log_value(full))

    out["currency"] = meta.get("currency")
    out["instrument_type"] = (
        meta.get("instrumentType") or meta.get("instrument_type") or meta.get("assetClass") or meta.get("asset_class")
    )
    out["name"] = out.get("name") or meta.get("name") or full
    # Canonical labels so per-holding consumers (e.g. /allocation) bucket the
    # same exposure together, matching the sector/region aggregates (#8530).
    out["sector"] = normalise_optional_sector(out.get("sector") or meta.get("sector"))
    out["region"] = normalise_optional_region(out.get("region") or meta.get("region"))
    if is_cash_instrument(full, out.get("instrument_type")):
        # Cash that _is_cash() doesn't catch (e.g. CASH.USD in a GBP account)
        # still gets the same "Cash" sector as aggregate_by_ticker rows (#8530).
        out["sector"] = CASH_SECTOR_LABEL
    out["asset_class"] = out.get("asset_class") or meta.get("assetClass") or meta.get("asset_class")

    units = float(out.get(UNITS, 0) or 0.0)
    if units <= 0:
        out.setdefault(COST_BASIS_GBP, None)
        out[EFFECTIVE_COST_BASIS_GBP] = 0.0
        out["market_value_gbp"] = 0.0
        out["gain_gbp"] = 0.0
        out["unrealised_gain_gbp"] = 0.0
        out["unrealized_gain_gbp"] = 0.0
        out["gain_pct"] = None
        out["day_change_gbp"] = 0.0
        out["days_held"] = None
        out["sell_eligible"] = False
        out["eligible_on"] = None
        out["days_until_eligible"] = None
        out["next_eligible_sell_date"] = None
        out["price"] = None
        out["current_price_gbp"] = None
        out["cost_basis_source"] = "none"
        return out

    # No transaction/lot date on record: leave it genuinely null instead of
    # substituting the price-history start date as a fabricated acquisition
    # date (#7220) -- every holding sharing that same synthetic date made
    # Acquired/Days Held/Stage/Eligible meaningless.
    out.setdefault(ACQUIRED_DATE, None)

    calc = calc or PricingDateCalculator(today=today)
    acq = _parse_date(out.get(ACQUIRED_DATE))
    pricing_date = calc.reporting_date

    if acq:
        days = (pricing_date - acq).days
        out["days_held"] = days
        hold_days = ucfg.hold_days_min or 0
        next_date_candidate = acq + dt.timedelta(days=hold_days)
        next_date = calc.resolve_weekday(next_date_candidate, forward=True)
        anchor = calc.today
        eligible = anchor >= next_date
        out["eligible_on"] = next_date.isoformat()
        out["next_eligible_sell_date"] = next_date.isoformat()
        out["days_until_eligible"] = max(0, (next_date - anchor).days)
    else:
        # Unknown acquisition date => eligibility is unknown too. Keep this
        # None rather than False so callers don't render a confident "not
        # eligible" verdict from a missing date (#7220).
        out["days_held"] = None
        eligible = None
        out["eligible_on"] = None
        out["days_until_eligible"] = None
        out["next_eligible_sell_date"] = None

    instr_type = (meta.get("instrumentType") or meta.get("instrument_type") or "").upper()
    asset_class = (meta.get("assetClass") or meta.get("asset_class") or "").upper()
    sector = (meta.get("sector") or "").upper()
    is_commodity = asset_class == "COMMODITY" or sector == "COMMODITY"
    is_etf = instr_type == "ETF"
    exempt_tickers = {t.upper() for t in (ucfg.approval_exempt_tickers or [])}
    exempt_types = {t.upper() for t in (ucfg.approval_exempt_types or [])}
    exempt_type = instr_type in exempt_types
    if is_etf and is_commodity:
        exempt_type = False
    needs_approval = not (ticker.upper() in exempt_tickers or full.upper() in exempt_tickers or exempt_type)

    approved = False
    if approvals and needs_approval:
        approved_on = approvals.get(full.upper()) or approvals.get(ticker.upper())
        if approved_on:
            approved = is_approval_valid(approved_on, today)

    out["sell_eligible"] = None if eligible is None else bool(eligible and (approved or not needs_approval))

    px = px_source = prev_px = None
    last_price_time = None
    is_stale = True
    out["forward_7d_change_pct"] = None
    out["forward_30d_change_pct"] = None

    if units != 0:
        from backend.common import portfolio_utils as pu  # local import to avoid circular

        snap = pu._PRICE_SNAPSHOT.get(full) or pu._PRICE_SNAPSHOT.get(ticker)
        snap_price = snap.get("last_price") if isinstance(snap, dict) else None
        if not is_nan(snap_price):
            px = float(snap["last_price"])
            last_price_time = snap.get("last_price_time")
            is_stale = _snapshot_is_stale(snap, calc.reporting_date)
            px_source = "snapshot"
            prev_date = calc.previous_pricing_date
        else:
            asof_date = calc.reporting_date
            px, px_source, px_date = _get_dated_price_for_date_scaled(ticker, exchange, asof_date, field="Close_gbp")
            # The range loader may have walked back to an earlier close; only a
            # row for the reporting date itself is fresh (#7919).
            is_stale = px_date is None or px_date < asof_date
            prev_date = calc.previous_pricing_date

        prev_px, _ = _get_price_for_date_scaled(ticker, exchange, prev_date, field="Close_gbp")

        if px is None and prev_px is not None:
            # Today's close is missing/unavailable (e.g. a gap in the price
            # source); fall back to the last known close instead of leaving
            # the holding unpriced.
            px = prev_px
            px_source = "previous_close"
            is_stale = True

        if px is not None:
            days_since = max(0, (dt.date.today() - pricing_date).days)
            if days_since >= 7:
                future_candidate = pricing_date + timedelta(days=7)
                future_date = calc.resolve_weekday(future_candidate, forward=True)
                if future_date > pricing_date:
                    future_px, _ = _get_price_for_date_scaled(ticker, exchange, future_date, field="Close_gbp")
                    if future_px is not None:
                        change = (future_px / px) - 1
                        out["forward_7d_change_pct"] = round(change * 100, 4)
            if days_since >= 30:
                future_candidate = pricing_date + timedelta(days=30)
                future_date = calc.resolve_weekday(future_candidate, forward=True)
                if future_date > pricing_date:
                    future_px, _ = _get_price_for_date_scaled(ticker, exchange, future_date, field="Close_gbp")
                    if future_px is not None:
                        change = (future_px / px) - 1
                        out["forward_30d_change_pct"] = round(change * 100, 4)

    out["price"] = px
    out["current_price_gbp"] = px
    out["latest_source"] = px_source
    out["last_price_time"] = last_price_time
    out["is_stale"] = is_stale

    helper = get_effective_cost_basis_gbp
    pass_price_hint = False
    try:
        signature = inspect.signature(helper)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        params = signature.parameters
        if "price_hint" in params:
            pass_price_hint = True
        else:
            pass_price_hint = any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())

    if pass_price_hint:
        ecb = helper(out, price_cache, price_hint=px)
    else:
        try:
            ecb = helper(out, price_cache, price_hint=px)
        except TypeError:
            ecb = helper(out, price_cache)

    out[EFFECTIVE_COST_BASIS_GBP] = ecb

    try:
        booked_cost = float(out.get(COST_BASIS_GBP) or 0.0)
    except (TypeError, ValueError):
        booked_cost = 0.0
    cost_for_gain = booked_cost if booked_cost > 0 else ecb

    # No usable cost (#8471): either nothing to derive one from, or the cost is
    # the last-resort guess of units * current price (cost_basis_source
    # "unknown", #7220). Any gain computed from it is made up -- 0.0 for the
    # guess, the whole market value for a zero cost -- so report it as unknown.
    # (book_suspect is flagged later by _flag_implausible_book_cost, which nulls
    # the gain fields itself.)
    cost_unknown = cost_for_gain <= 0 or (booked_cost <= 0 and is_cost_basis_unreliable(out.get("cost_basis_source")))

    if px is not None:
        mv = round(units * float(px), 2)
        out["market_value_gbp"] = mv
        out["gain_gbp"] = None if cost_unknown else round(mv - cost_for_gain, 2)
        out["unrealised_gain_gbp"] = out["gain_gbp"]
        out["unrealized_gain_gbp"] = out["gain_gbp"]
        out["gain_pct"] = None if cost_unknown else (mv - cost_for_gain) / cost_for_gain * 100.0
    else:
        out["market_value_gbp"] = None
        out["gain_gbp"] = None
        out["unrealised_gain_gbp"] = None
        out["unrealized_gain_gbp"] = None
        out["gain_pct"] = None

    if px is not None and prev_px is not None:
        change_val = (px - prev_px) * units
        out["day_change_gbp"] = round(change_val, 2)
    else:
        out["day_change_gbp"] = None

    # get_effective_cost_basis_gbp() may already have tagged out["cost_basis_source"]
    # as "unknown" (no booked cost, no acquisition date, no cached historical
    # price -- cost was set equal to the current price as a last resort, see
    # #7220). That is a materially different claim from a real historical
    # derivation, so it must not be overwritten with the generic "derived"
    # here once a booked cost is ruled out.
    if float(out.get(COST_BASIS_GBP) or 0.0) > 0:
        out["cost_basis_source"] = "book"
    elif out.get("cost_basis_source") != "unknown":
        out["cost_basis_source"] = "derived"

    _flag_implausible_book_cost(out, units, ticker, exchange, acq, px, price_cache)
    return out


def _is_cash(full: str, account_ccy: str = "GBP") -> bool:
    f = (full or "").upper()
    return f in {f"CASH.{account_ccy}", f"{account_ccy}.CASH", "CASH"}


def _cash_name(full: str, account_ccy: str = "GBP") -> str:
    return f"Cash ({account_ccy})"
