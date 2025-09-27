"""
Meta time-series fetcher that transparently tries Yahoo -> Stooq -> Alpha Vantage -> FT
and merges the first successful result. Helpers return snapshots
(last price, 7-day %, 30-day %).

2025-08-04 - smarter merge:
  - Fetch Yahoo first; if coverage < 95 % of the requested window,
    supplement from Stooq, Alpha Vantage, then FT.
  - Added ticker sanity-check and quieter logging for expected fall-backs.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta, datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict, Tuple

import pandas as pd

from backend import config

OFFLINE_MODE = config.offline_mode

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_stooq_timeseries import (
    fetch_stooq_timeseries_range,
    StooqRateLimitError,
)
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
from backend.timeseries.fetch_alphavantage_timeseries import (
    fetch_alphavantage_timeseries_range,
    AlphaVantageRateLimitError,
)
from backend.utils.timeseries_helpers import (
    _nearest_weekday,
    _is_isin,
    STANDARD_COLUMNS,
)
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker

logger = logging.getLogger("meta_timeseries")

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
_TICKER_RE = re.compile(r"^[A-Za-z0-9]{1,12}(?:[-\.][A-Z]{1,3})?$")


_DEFAULT_INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"
INSTRUMENTS_DIR = _DEFAULT_INSTRUMENTS_DIR


def _instrument_dirs() -> list[Path]:
    """Return candidate directories that may contain instrument metadata."""

    candidates: list[Path] = []
    data_root = getattr(config, "data_root", None)

    # When the module level ``INSTRUMENTS_DIR`` is overridden (for example in
    # tests), treat it as authoritative and avoid falling back to the default
    # repository metadata. This prevents unrelated fixtures on the host machine
    # from influencing lookups while still allowing ``config.data_root`` to
    # redirect metadata when the default location is in use.
    if INSTRUMENTS_DIR != _DEFAULT_INSTRUMENTS_DIR:
        candidates.append(INSTRUMENTS_DIR)
    else:
        if data_root:
            candidates.append(Path(data_root) / "instruments")
        candidates.append(INSTRUMENTS_DIR)

    seen: set[Path] = set()
    resolved: list[Path] = []
    for candidate in candidates:
        try:
            resolved_path = Path(candidate).expanduser().resolve()
        except OSError:
            continue
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        try:
            if resolved_path.is_dir():
                resolved.append(resolved_path)
        except OSError:
            continue
    return resolved


def _resolve_exchange_from_metadata(symbol: str) -> str:
    """Return exchange code for *symbol* using instrument metadata if possible."""

    dirs = tuple(str(path) for path in _instrument_dirs())
    return _resolve_exchange_from_metadata_cached(symbol.upper(), dirs)


@lru_cache(maxsize=2048)
def _resolve_exchange_from_metadata_cached(
    symbol: str, directories: tuple[str, ...]
) -> str:
    """Cached helper that scopes lookups to the active instrument directories."""

    for root_str in directories:
        root = Path(root_str)
        try:
            for ex_dir in root.iterdir():
                if not ex_dir.is_dir() or ex_dir.name.lower() == "cash":
                    continue
                try:
                    if (ex_dir / f"{symbol}.json").is_file():
                        return ex_dir.name.upper()
                except OSError:
                    continue
        except OSError:
            continue
    return ""


def _resolve_symbol_exchange_details(
    ticker: str, exchange: str | None
) -> Tuple[str, str, str]:
    """Return symbol, resolved exchange and metadata exchange."""

    sym, suffix = (re.split(r"[._]", ticker, 1) + [""])[:2]
    provided = (exchange or "").upper()
    suffix = suffix.upper()
    if suffix and provided and suffix != provided:
        logger.debug(
            "Exchange mismatch for %s: suffix %s vs argument %s", ticker, suffix, provided
        )
    resolved = suffix or provided

    meta_ex = _resolve_exchange_from_metadata(sym).upper()
    ex = resolved
    if not ex and meta_ex:
        ex = meta_ex
        logger.debug("Resolved exchange for %s via metadata: %s", sym, ex)
    elif ex and meta_ex and ex != meta_ex:
        logger.debug(
            "Exchange metadata mismatch for %s: using %s but metadata %s",
            sym,
            ex,
            meta_ex,
        )
    elif not ex:
        logger.debug("No exchange information for %s; continuing without exchange", sym)

    return sym.upper(), (ex or "").upper(), meta_ex


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> Tuple[str, str]:
    """Resolve base symbol and exchange from inputs and metadata."""

    sym, ex, _ = _resolve_symbol_exchange_details(ticker, exchange)
    return sym, ex


def _resolve_loader_exchange(
    ticker: str, exchange_arg: str | None, symbol: str, resolved_exchange: str
) -> str:
    """Return the exchange to use when fetching cached data.

    Explicit suffixes and ``exchange`` arguments take priority, otherwise fall
    back to the previously resolved exchange (which may come from metadata).
    """

    parts = re.split(r"[._]", ticker, 1)
    suffix = parts[1].strip().upper() if len(parts) == 2 else ""
    provided = (exchange_arg or "").strip().upper()
    resolved = (resolved_exchange or "").strip().upper()

    if provided:
        # ``resolved_exchange`` already respects explicit overrides, but we
        # normalise again defensively in case the caller passed a lowercase
        # string and resolution fell back to metadata.
        return resolved or provided

    if suffix:
        return resolved or suffix

    return resolved


def _merge(sources: List[pd.DataFrame]) -> pd.DataFrame:
    if not sources:
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    df = pd.concat(sources, ignore_index=True)
    df = df.drop_duplicates(subset=["Date", "Close"], keep="last")
    return df.sort_values("Date").reset_index(drop=True)


def _coverage_ratio(df: pd.DataFrame,
                    expected: set[date]) -> float:
    if df.empty or not expected:
        return 0.0
    present = set(pd.to_datetime(df["Date"]).dt.date)
    return len(present & expected) / len(expected)

# ──────────────────────────────────────────────────────────────
# Core fetch
# ──────────────────────────────────────────────────────────────
def fetch_meta_timeseries(
    ticker: str,
    exchange: str = "",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    *,
    min_coverage: float = 0.95,          # 95 % of trading days
) -> pd.DataFrame:
    """
    Fetch price history from Yahoo, Stooq, FT - only as much as needed.

    Returns DF[Date, Open, High, Low, Close, Volume, Ticker, Source].
    """
    # ── Guard rails & resolution ───────────────────────────────
    if not ticker or not ticker.strip():
        logger.warning("Ticker pattern looks invalid: empty or whitespace")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    if not _TICKER_RE.match(ticker):
        logger.warning("Ticker pattern looks invalid: %s", ticker)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    raw_ticker = ticker
    ticker, exchange = _resolve_ticker_exchange(ticker, exchange)
    logger.debug("Resolved %s to %s.%s", raw_ticker, ticker, exchange)

    if end_date is None:
        end_date = date.today() - timedelta(days=1)
    if start_date is None:
        start_date = end_date - timedelta(days=365)

    start_date = _nearest_weekday(start_date, forward=False)
    end_date   = _nearest_weekday(end_date,   forward=True)

    if ticker.upper() == "CASH" or exchange.upper() == "CASH":
        dates = pd.bdate_range(start_date, end_date)
        df = pd.DataFrame(
            {
                "Date": dates,
                "Open": 1.0,
                "High": 1.0,
                "Low": 1.0,
                "Close": 1.0,
                "Volume": 0.0,
                "Ticker": f"{ticker}.{exchange}",
                "Source": "cash",
            }
        )
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        return df

    if not is_valid_ticker(ticker, exchange):
        logger.info("Skipping unrecognized ticker %s.%s", ticker, exchange)
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    # Weekday grid we want to fill
    expected_dates = set(pd.bdate_range(start_date, end_date).date)

    data: list[pd.DataFrame] = []

    if _is_isin(ticker=ticker):
        ft_df = fetch_ft_df(ticker, end_date, start_date)

        if not ft_df.empty:
            return ft_df

    # ── 1 · Yahoo ─────────────────────────────────────────────
    try:
        yahoo = fetch_yahoo_timeseries_range(ticker, exchange,
                                             start_date, end_date)
        if not yahoo.empty:
            data.append(yahoo)
            if _coverage_ratio(yahoo, expected_dates) >= min_coverage:
                return yahoo
    except Exception as exc:
        logger.debug("Yahoo miss for %s.%s: %s", ticker, exchange, exc)

    # ── 2 · Stooq (fill gaps only if needed) ──────────────────
    try:
        stooq = fetch_stooq_timeseries_range(ticker, exchange,
                                             start_date, end_date)
        if not stooq.empty:
            combined = _merge([*data, stooq])
            if _coverage_ratio(combined, expected_dates) >= min_coverage:
                return combined
            data.append(stooq)
    except StooqRateLimitError as exc:
        logger.debug("Stooq rate limit for %s.%s: %s", ticker, exchange, exc)
    except Exception as exc:
        logger.debug("Stooq miss for %s.%s: %s", ticker, exchange, exc)

    # ── 3 · Alpha Vantage (fill gaps if still needed) ─────────
    if config.alpha_vantage_enabled:
        try:
            av = fetch_alphavantage_timeseries_range(
                ticker, exchange, start_date, end_date
            )
            if not av.empty:
                combined = _merge([*data, av])
                if _coverage_ratio(combined, expected_dates) >= min_coverage:
                    return combined
                data.append(av)
        except AlphaVantageRateLimitError as exc:
            logger.debug("Alpha Vantage rate limit for %s.%s: %s", ticker, exchange, exc)
            if exc.retry_after:
                time.sleep(exc.retry_after)
        except Exception as exc:
            logger.debug("Alpha Vantage miss for %s.%s: %s", ticker, exchange, exc)
    else:
        logger.debug("Alpha Vantage disabled; skipping for %s.%s", ticker, exchange)

    # ── 4 · FT fallback – last resort ─────────────────────────
    ft_df = fetch_ft_df(ticker, end_date, start_date)

    if not ft_df.empty:
        data.append(ft_df)

    if not data:
        logger.info("No data sources succeeded for %s.%s",
                    ticker, exchange)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = _merge(data)
    # Ensure we compare like-for-like datatypes. Some sources (e.g. FT) may
    # return plain ``datetime.date`` objects which cannot be directly
    # compared against ``pd.Timestamp``. Convert the column on the fly to
    # Timestamp before applying the end-date filter.
    df = df[pd.to_datetime(df["Date"]) <= pd.to_datetime(end_date)]
    return df


def fetch_ft_df(ticker, end_date, start_date):
    try:
        logger.debug(f"Falling back to FT for {ticker}")
        days = (end_date - start_date).days or 1
        ft_df = fetch_ft_timeseries(ticker, days)
        return ft_df
    except Exception as exc:
        logger.debug("FT miss for %s: %s", ticker, exc)
        return pd.DataFrame(columns=STANDARD_COLUMNS)

# ──────────────────────────────────────────────────────────────
# Cache-aware batch helpers (local import) ─────────────────────
def run_all_tickers(
    tickers: List[str], exchange: str = "", days: int = 365
) -> List[str]:
    """Warm-up helper - returns tickers that produced data.

    ``tickers`` may contain base symbols ("VOD") or full tickers ("VOD.L").
    When a ticker includes an exchange suffix, it takes precedence over the
    ``exchange`` argument. If neither provides an exchange, resolve via
    instrument metadata.
    """
    from backend.timeseries.cache import load_meta_timeseries
    import time

    ok: list[str] = []
    delay = 0.0
    if getattr(config, "stooq_requests_per_minute", None):
        try:
            rpm = float(config.stooq_requests_per_minute)
            if rpm > 0:
                delay = 60.0 / rpm
        except Exception:
            pass

    for idx, t in enumerate(tickers):
        if delay and idx:
            time.sleep(delay)
        sym, ex, meta_exchange = _resolve_symbol_exchange_details(t, exchange)
        logger.debug("run_all_tickers resolved %s -> %s.%s", t, sym, ex)
        loader_exchange = _resolve_loader_exchange(t, exchange, sym, ex)
        cache_exchange = meta_exchange or loader_exchange or ""
        if meta_exchange and loader_exchange and loader_exchange != meta_exchange:
            logger.debug(
                "Cache exchange mismatch for %s: loader %s vs metadata %s",
                sym,
                loader_exchange,
                meta_exchange or "<empty>",
            )
        try:
            if not load_meta_timeseries(sym, cache_exchange, days).empty:
                ok.append(t)
        except Exception as exc:
            logger.warning("[WARN] %s: %s", t, exc)
    logger.info(
        "Bulk warm-up complete: %d updated, %d skipped", len(ok), len(tickers) - len(ok)
    )
    return ok


def load_timeseries_data(
    tickers: List[str], exchange: str = "", days: int = 365
) -> Dict[str, pd.DataFrame]:
    """Return {ticker: dataframe} using the parquet cache."""
    from backend.timeseries.cache import load_meta_timeseries
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        sym, ex, meta_exchange = _resolve_symbol_exchange_details(t, exchange)
        logger.debug("load_timeseries_data resolved %s -> %s.%s", t, sym, ex)
        loader_exchange = _resolve_loader_exchange(t, exchange, sym, ex)
        cache_exchange = meta_exchange or loader_exchange or ""
        if meta_exchange and loader_exchange and loader_exchange != meta_exchange:
            logger.debug(
                "Cache exchange mismatch for %s: loader %s vs metadata %s",
                sym,
                loader_exchange,
                meta_exchange or "<empty>",
            )
        try:
            df = load_meta_timeseries(sym, cache_exchange, days)
            if not df.empty:
                out[t] = df
        except Exception as exc:
            logger.warning("Load fail %s: %s", t, exc)
    logger.info(
        "Bulk load complete: %d updated, %d skipped", len(out), len(tickers) - len(out)
    )
    return out


# ─────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    # Example usage
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)

    df = fetch_meta_timeseries("1", "", start_date=cutoff, end_date=today)
    print("Returned: %s", df.head())

