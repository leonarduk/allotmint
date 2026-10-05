"""
Price utilities driven entirely by the live portfolio universe
(no securities.csv required).  Persists a JSON snapshot with:

    {
      "TICKER": {
        "last_price":      ...,
        "price_currency":  "GBP" | None,
        "change_7d_pct":   ...,
        "change_30d_pct":  ...,
        "last_price_date": "YYYY-MM-DD",
        "last_price_time": "YYYY-MM-DDTHH:MM:SSZ",
        "is_stale":        true
      },
      ...
    }

Note on price_currency semantics
---------------------------------
* ``load_live_prices`` returns GBP-normalised prices, so live snapshots emit
  ``price_currency = "GBP"``.
* ``_load_latest_closes`` also returns GBP-normalised prices, so fallback
  snapshots emit ``price_currency = "GBP"``.

Note on is_stale semantics (#8595)
----------------------------------
* A live quote is fresh while its timestamp is under 15 minutes old.
* A last close is fresh when it is from the latest completed trading day
  (``PricingDateCalculator.reporting_date``); older closes are stale.
  ``last_price_date`` carries the close's own date so consumers can show it.
* A live quote reports the latest trading day as ``last_price_date`` (the
  day its 7/30-day changes are anchored to); ``last_price_time`` carries the
  quote's own timestamp.
* An entry with no price reports ``last_price_date = None``.
* When no price is available, ``price_currency`` is ``None``.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

import pandas as pd

from backend import price_triggers
from backend.common import instrument_api, refresh_progress
from backend.common.currency import CurrencyNormaliser
from backend.common.holding_utils import load_latest_closes as _load_latest_closes
from backend.common.holding_utils import load_live_prices
from backend.common.numeric_utils import is_nan
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    DATA_BUCKET_ENV,
    PRICES_S3_KEY,
    check_price_alerts,
    list_all_unique_tickers,
    refresh_snapshot_in_memory,
)

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.boe_rates import refresh_boe_series
from backend.timeseries.cache import load_meta_timeseries_range, refresh_fx_cache_for_tickers
from backend.utils.pricing_dates import PricingDateCalculator
from backend.utils.timeseries_helpers import _nearest_weekday

logger = logging.getLogger(__name__)

# Scopes refresh_progress reporting to the exact call chain started by
# refresh_prices(), rather than to get_price_snapshot's signature: other
# callers of get_price_snapshot (there are none today, but the contract
# should hold regardless) keep their normal signature and simply never opt
# in, so they can't corrupt an in-flight refresh's progress with an
# unrelated, differently-sized ticker list. Thread-local by construction
# (a plain synchronous call within refresh_prices()'s own worker thread),
# so concurrent requests on other threads are unaffected.
_REPORT_PROGRESS: contextvars.ContextVar[bool] = contextvars.ContextVar("refresh_progress_reporting", default=False)


@contextmanager
def _reporting_progress() -> Iterator[None]:
    token = _REPORT_PROGRESS.set(True)
    try:
        yield
    finally:
        _REPORT_PROGRESS.reset(token)


def _close_on(sym: str, exch: str, d: date) -> Optional[float]:
    """Fetch the close price in GBP for ``sym.exch`` on or nearest before ``d``.

    Non-GBP closes are converted via CurrencyNormaliser + ``_fx_to_base``.
    Pence-denominated instruments (GBX / GBXP / GBp / GBpx) are scaled to GBP
    through the same conversion path used elsewhere.
    """

    snap = _nearest_weekday(d, forward=False)
    df = load_meta_timeseries_range(sym, exch, start_date=snap, end_date=snap)
    if df is None or df.empty:
        return None

    name_map = {c.lower(): c for c in df.columns}
    close_col = (
        name_map.get("close_gbp") or name_map.get("close") or name_map.get("adj close") or name_map.get("adj_close")
    )
    if not close_col:
        return None

    try:
        value = float(df[close_col].iloc[0])
    except Exception:
        return None

    if is_nan(value):
        return None

    if close_col.lower() != "close_gbp":
        from backend.common.instruments import get_instrument_meta
        from backend.common.portfolio_utils import _fx_to_base

        meta = get_instrument_meta(f"{sym}.{exch}") or get_instrument_meta(sym) or {}
        raw_currency = str(meta.get("currency") or "GBP").strip()
        normaliser = CurrencyNormaliser.from_raw(raw_currency)
        try:
            value = normaliser.to_gbp(value, {}, _fx_to_base)
        except ValueError:
            return None

    return value


def get_price_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Return last price and 7/30 day % changes for each ticker.

    Uses cached meta timeseries data; callers are responsible for priming the
    cache via ``fetch_meta_timeseries`` beforehand. Missing data results in
    ``None`` values so downstream consumers can skip incomplete entries.

    ``price_currency`` reflects the *actual* currency of ``last_price``:
    - Live-price path: ``load_live_prices`` already converts to GBP → "GBP".
    - Last-close fallback: ``_load_latest_closes`` already converts to GBP
      → "GBP".
    - No-data path: ``None`` (last_price is also None; consumers should skip).

    Reports ``refresh_progress`` for its ``_load_latest_closes`` call only
    when invoked through :func:`refresh_prices`'s ``_reporting_progress``
    context — see the module-level note there for why this is scoped by
    context rather than by a parameter here.
    """

    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    last_trading_day = calc.reporting_date
    latest_kwargs = {"report_progress": True} if _REPORT_PROGRESS.get() else {}
    latest_closes = _load_latest_closes(list(tickers), **latest_kwargs)
    latest = {key: price for key, (price, _close_date) in latest_closes.items()}
    live = load_live_prices(list(tickers))
    now = datetime.now(UTC)

    snapshot: Dict[str, Dict] = {}
    for full in tickers:
        live_info = live.get(full.upper())
        last_close, close_date = latest_closes.get(full, (None, None))
        price = None
        ts: Optional[datetime] = None
        price_date: Optional[date] = None
        is_stale = True
        # price_currency tracks the currency denomination of `price`.
        # Both live and last-close sources are GBP-normalised at this point.
        # None means no price data was available at all.
        price_currency: Optional[str]

        if live_info:
            live_price = live_info.get("price")
            price = float(live_price) if live_price is not None else None
            if is_nan(price):
                price = None
            ts = live_info.get("timestamp")
            if ts:
                is_stale = (now - ts) > timedelta(minutes=15)
            # Live quotes are dated by the trading day their 7/30-day changes
            # are anchored to; last_price_time carries the quote's own time.
            price_date = last_trading_day
            # load_live_prices converts to GBP internally
            price_currency = "GBP"
        elif not is_nan(last_close):
            price = float(last_close)
            # A close from the latest completed trading day is fresh; only an
            # older (or undated) close is stale (#8595). A close dated after
            # the trading day (feed clock ahead of ours) is not older, so fresh.
            price_date = close_date
            is_stale = close_date is None or close_date < last_trading_day
            # _load_latest_closes already normalises to GBP.
            price_currency = "GBP"
        else:
            # No price data available. Emit None so consumers can distinguish
            # "priced at GBP" from "no data" without guessing.
            price_currency = None

        info = {
            "last_price": price,
            "price_currency": price_currency,
            "change_7d_pct": None,
            "change_30d_pct": None,
            "last_price_date": price_date.isoformat() if price is not None and price_date else None,
            "last_price_time": ts.isoformat().replace("+00:00", "Z") if ts else None,
            "is_stale": is_stale,
        }

        if price is not None:
            resolved = instrument_api._resolve_full_ticker(full, latest)
            if resolved:
                sym, exch = resolved
            else:
                sym = full.split(".", 1)[0]
                exch = "L"
                logger.debug("Could not resolve exchange for %s; defaulting to L", full)

            px_7_candidate = calc.reporting_date - timedelta(days=7)
            px_30_candidate = calc.reporting_date - timedelta(days=30)

            px_7 = _close_on(sym, exch, px_7_candidate)
            px_30 = _close_on(sym, exch, px_30_candidate)

            if px_7 not in (None, 0):
                info["change_7d_pct"] = (float(price) / px_7 - 1.0) * 100.0
            if px_30 not in (None, 0):
                info["change_30d_pct"] = (float(price) / px_30 - 1.0) * 100.0

        snapshot[full] = info

    return snapshot


# ──────────────────────────────────────────────────────────────
# Securities universe : derived from portfolios
# ──────────────────────────────────────────────────────────────
def _resolve_instrument_type(ticker: str, holding: Optional[Dict] = None) -> Optional[str]:
    """Resolve ``instrument_type`` for ``ticker`` from canonical metadata.

    Raw holding documents -- including the ones produced by the supported
    CSV-import and transaction-rebuild paths -- usually do not carry
    ``instrument_type``, and default Screener watchlist symbols may have no
    holding at all. Canonical instrument metadata (with its camelCase and
    ``asset_class`` fallbacks) is therefore the primary source; the raw
    holding value is only used when canonical metadata has nothing.
    """

    from backend.common.instrument_classification import resolve_instrument_type
    from backend.common.instruments import get_instrument_meta, resolve_instrument_ticker

    resolved_ticker = resolve_instrument_ticker(ticker, create_missing=False) or ticker
    meta = get_instrument_meta(resolved_ticker) or {}
    # Case-insensitive asset-class fallback: legacy "Equity" == "equity" (#9196).
    resolved = resolve_instrument_type(meta)
    if resolved:
        return resolved
    if holding is not None:
        return holding.get("instrument_type")
    return None


def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    portfolios = list_portfolios()
    logger.debug("Loaded %d portfolios", len(portfolios))
    for pf in portfolios:
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name": h.get("name", tkr),
                    "instrument_type": _resolve_instrument_type(tkr, h),
                }
    return securities


# Not built eagerly at import time / on every call: _build_securities_from_portfolios()
# does a full portfolios/accounts/holdings scan plus a _resolve_instrument_type()
# lookup (potential S3 GetObject) per distinct holding ticker. Without caching,
# a screener request iterating ~500 result rows -- each calling get_security_meta()
# once -- reran that full rebuild up to 500x per request. Cached lazily on first
# use per process, mirroring the _SECURITIES precedent in portfolio_utils.py.
_SECURITIES: Dict[str, Dict] | None = None
# RLock (not Lock): _build_securities_from_portfolios() calls into
# list_portfolios(), and a future change could end up calling get_security_meta()
# again before _SECURITIES is set. A plain Lock would deadlock that case; RLock
# lets the same thread re-enter.
_SECURITIES_LOCK = threading.RLock()


def get_security_meta(ticker: str) -> Optional[Dict]:
    """Return metadata derived from latest portfolios, cached per process.

    Falls back to canonical instrument metadata for tickers that are not
    held in any portfolio at all (e.g. watchlist-only Screener symbols), so
    callers still receive a resolvable ``instrument_type`` for them.
    """
    global _SECURITIES
    if _SECURITIES is None:
        with _SECURITIES_LOCK:
            if _SECURITIES is None:
                _SECURITIES = _build_securities_from_portfolios()
    t = ticker.upper()
    meta = _SECURITIES.get(t)
    if meta:
        return meta
    instrument_type = _resolve_instrument_type(t)
    if instrument_type is None:
        return None
    return {"ticker": t, "name": t, "instrument_type": instrument_type}


# ──────────────────────────────────────────────────────────────
# In-memory latest-price cache (GBP closes only)
# ──────────────────────────────────────────────────────────────
_price_cache: Dict[str, float] = {}


def get_price_gbp(ticker: str) -> Optional[float]:
    """Return the cached last close in GBP, or None if unseen."""
    return _price_cache.get(ticker.upper())


# ──────────────────────────────────────────────────────────────
# Refresh logic
# ──────────────────────────────────────────────────────────────
def refresh_universe() -> List[str]:
    """Return every ticker the scheduled price refresh keeps fresh.

    That is held tickers (real and virtual portfolios) plus tickers watched by
    an enabled price trigger. A cached series outside this set is never
    refreshed, which the Data Quality report uses to tell a failing refresh
    apart from an orphaned cache file (#8599).
    """
    tickers: List[str] = list_all_unique_tickers()
    try:
        # Watched tickers are priced too so a trigger on a non-held ticker can fire.
        tickers = sorted(set(tickers) | set(price_triggers.watched_tickers()))
    except Exception as exc:  # trigger problems must not fail the price refresh
        logger.error("Could not load price trigger tickers: %s", sanitise_log_value(exc))
    return tickers


def put_empty_snapshot_if_absent(client, bucket: str) -> bool:
    """Write ``{}`` to ``PRICES_S3_KEY`` only if no snapshot exists; return whether it wrote.

    Uses an S3 conditional write (``IfNoneMatch="*"``), so the existence check
    and the write are one atomic call: a missing key is always created (the
    post-deploy check needs it, #3685) and an existing snapshot -- however it
    got there -- is never replaced with ``{}`` (#8805). Other errors raise.
    """
    try:
        client.put_object(
            Bucket=bucket,
            Key=PRICES_S3_KEY,
            Body=b"{}",
            ContentType="application/json",
            IfNoneMatch="*",
        )
        return True
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
        # 412: the key exists. 409: a concurrent write to the key won the race.
        if code in {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}:
            return False
        raise


def _upload_snapshot_to_s3(merged: Dict) -> None:
    """Upload ``merged`` as the shared snapshot, never replacing one with ``{}``.

    The key must always exist after a refresh so post-deploy checks don't wait
    forever (#3685). But an empty ``merged`` -- nothing fetched and no local
    seed, the normal case in a fresh Lambda container -- is only written when
    no snapshot exists yet (an atomic conditional write); overwriting a good
    snapshot with ``{}`` left every holding without a snapshot price (#8805).
    """
    _s3_bucket = os.getenv(DATA_BUCKET_ENV)
    if not _s3_bucket:
        logger.warning("DATA_BUCKET not set; skipping S3 upload of price snapshot")
        return
    try:
        import boto3  # type: ignore

        client = boto3.client("s3")
        if not merged:
            if put_empty_snapshot_if_absent(client, _s3_bucket):
                logger.warning("No prices fetched; seeded an empty S3 price snapshot because none existed")
            else:
                logger.error("No prices fetched; keeping the existing S3 price snapshot rather than uploading {}")
            return
        client.put_object(
            Bucket=_s3_bucket,
            Key=PRICES_S3_KEY,
            Body=json.dumps(merged, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info(
            "Uploaded price snapshot to s3://%s/%s", sanitise_log_value(_s3_bucket), sanitise_log_value(PRICES_S3_KEY)
        )
    except Exception as exc:
        if merged:
            # The previous snapshot, if any, is still in place.
            logger.warning("Failed to upload price snapshot to S3: %s", sanitise_log_value(exc))
        else:
            # The conditional seed failed for a reason other than "key exists", so
            # the key may be missing and the post-deploy check will fail (#3685, #8943).
            logger.error(
                "Failed to seed a missing S3 price snapshot; the key may not exist: %s", sanitise_log_value(exc)
            )


def _refresh_reference_data(tickers: List[str]) -> None:
    """Refresh the FX cache and the stored Bank of England series alongside the prices.

    Page requests convert non-GBP closes from the FX cache only (#7917), and
    MCP tools read FX history and BoE rates from the data root only (#9322).
    A failure here must not stop the price snapshot being persisted.
    """
    try:
        refresh_fx_cache_for_tickers(tickers)
    except Exception as exc:
        logger.warning("FX cache refresh failed: %s", sanitise_log_value(exc))
    if config.offline_mode:
        return
    try:
        refresh_boe_series()
    except Exception as exc:
        logger.warning("Bank of England rates refresh failed: %s", sanitise_log_value(exc))


def refresh_prices() -> Dict:
    """
    Pulls latest close, 7- and 30-day % moves for every ticker in
    the current portfolios.  Writes to JSON and updates the cache.
    """
    tickers = refresh_universe()
    if not tickers:
        # Nothing held or watched is almost always a discovery failure (e.g.
        # owners hidden from a user-less job, #8805), not a real empty book.
        logger.error("Price refresh universe is empty: no held or watched tickers found")
    logger.info("Updating price snapshot for: %s", [sanitise_log_value(t) for t in tickers])

    refresh_progress.start(len(tickers))
    try:
        with _reporting_progress():
            snapshot = get_price_snapshot(tickers)
    finally:
        refresh_progress.finish()

    _refresh_reference_data(tickers)

    # ---- persist to disk --------------------------------------------------
    if not config.prices_json:
        raise RuntimeError("config.prices_json not configured")
    path = Path(config.prices_json)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Merge strategy: only write entries where we successfully fetched a finite,
    # positive price. This preserves existing seed/cached prices for tickers that
    # returned None or a non-finite value (offline mode, market closed,
    # data-source outage) rather than trashing them.
    to_persist = {
        t: v
        for t, v in snapshot.items()
        if v.get("last_price") is not None and pd.notna(v.get("last_price")) and v.get("last_price") > 0
    }
    existing: Dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    if to_persist:
        merged = {**existing, **to_persist}
        path.write_text(json.dumps(merged, indent=2))
    else:
        merged = existing
        logger.info(
            "Skipping local snapshot write — no valid prices fetched" " (offline mode or data-source unavailable)"
        )

    # ---- persist to S3 (primary store read by all Lambda instances) ---------
    if config.app_env == "aws":
        _upload_snapshot_to_s3(merged)

    # ---- refresh in-memory cache -----------------------------------------
    # Use merged (which includes preserved seed prices) when available; leave
    # the existing in-memory state intact when no prices were fetched so a
    # null-producing offline refresh does not trash valid cached entries.
    if to_persist:
        # merged = existing (disk) overwritten by to_persist (fresh, non-null).
        # existing entries come from our own prior writes so are already non-null;
        # any manually-corrupted null in existing is harmless — it will be
        # overwritten on the next successful refresh for that ticker.
        _price_cache.clear()
        for tkr, info in merged.items():
            _price_cache[tkr.upper()] = info["last_price"]
        refresh_snapshot_in_memory(merged)
    check_price_alerts()
    try:
        price_triggers.evaluate({t: (info or {}).get("last_price") for t, info in snapshot.items()})
    except Exception as exc:  # trigger problems must not fail the price refresh
        logger.error("Price trigger evaluation failed: %s", sanitise_log_value(exc))

    logger.debug("Snapshot written to %s", sanitise_log_value(path))
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "tickers": tickers,
        "snapshot": snapshot,
        "timestamp": ts,
    }


# ──────────────────────────────────────────────────────────────
# Ad-hoc helpers
# ──────────────────────────────────────────────────────────────
def load_latest_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Convenience helper for notebooks / quick scripts:
    returns {'TICKER': last_close_gbp, ...}
    """
    if not tickers:
        return {}
    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    start_candidate = calc.today - timedelta(days=365)
    end_candidate = calc.today - timedelta(days=1)
    start_date = calc.resolve_weekday(start_candidate, forward=False)
    end_date = calc.resolve_weekday(end_candidate, forward=False)

    prices: Dict[str, float] = {}
    for full in tickers:
        resolved = instrument_api._resolve_full_ticker(full, prices)
        if resolved:
            ticker_only, exchange = resolved
        else:
            ticker_only = full.split(".", 1)[0]
            exchange = "L"
            logger.debug("Could not resolve exchange for %s; defaulting to L", full)
        df = load_meta_timeseries_range(ticker_only, exchange, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            prices[full] = float(df.iloc[-1]["close"])
    return prices


def load_prices_for_tickers(
    tickers: Iterable[str],
    days: int = 365,
) -> pd.DataFrame:
    """
    Fetch historical daily closes for a list of tickers and return a
    concatenated dataframe; keeps each original suffix (e.g. '.L').
    """
    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    start_date, end_date = calc.lookback_range(days, end=calc.today, forward_end=True)

    ticker_list = list(tickers)

    def _fetch_one(full: str) -> Optional[pd.DataFrame]:
        try:
            resolved = instrument_api._resolve_full_ticker(full, {})
            if resolved:
                ticker_only, exchange = resolved
            else:
                ticker_only = full.split(".", 1)[0]
                exchange = "L"
                logger.debug("Could not resolve exchange for %s; defaulting to L", full)
            df = load_meta_timeseries_range(ticker_only, exchange, start_date=start_date, end_date=end_date)
            if not df.empty:
                df = df.copy()
                df["Ticker"] = full  # restore suffix for display
                return df
        except Exception as exc:
            logger.warning("Failed to fetch prices for %s: %s", sanitise_log_value(full), sanitise_log_value(exc))
        return None

    # load_meta_timeseries_range is I/O-bound (S3 read, occasionally a live
    # provider fetch on a cache miss) and independent per ticker, so fetch
    # every ticker concurrently rather than one at a time -- for a 10-ticker
    # portfolio this was ~6-12s sequential, confirmed live against
    # production. The underlying cache layer already locks its shared
    # LRU/mtime state (backend/timeseries/cache.py), so this is safe.
    frames: List[pd.DataFrame] = []
    if ticker_list:
        with ThreadPoolExecutor(max_workers=min(8, len(ticker_list))) as pool:
            for df in pool.map(_fetch_one, ticker_list):
                if df is not None:
                    frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ──────────────────────────────────────────────────────────────
# CLI test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(refresh_prices(), indent=2))
