import logging
from datetime import date, timedelta
from io import StringIO
from time import monotonic

import pandas as pd
import requests

from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

logger = logging.getLogger("stooq_timeseries")

BASE_URL = "https://stooq.com/q/d/l/"


class StooqRateLimitError(RuntimeError):
    """Raised when the Stooq daily hit limit has been exceeded."""


# Stooq requests are disabled until this date if the rate limit is hit
STOOQ_DISABLED_UNTIL: date = date.min

# After a connection-level failure (connect timeout, DNS/TLS error, refused or
# dropped connection), skip Stooq for this many seconds so an unreachable host
# costs one timeout per window rather than one per fetch (#7877). Tracked on the
# monotonic clock so wall-clock changes can't extend it.
STOOQ_UNREACHABLE_COOLDOWN_SECONDS = 600
_STOOQ_UNREACHABLE_UNTIL: float = 0.0

# A read timeout means the host accepted the connection but was slow for one
# ticker, so only that ticker is skipped for this long (#7913). If this many read
# timeouts happen in a row with no response in between, the host is treated as
# unreachable and the global cooldown starts.
STOOQ_TICKER_SKIP_SECONDS = 600
STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN = 3
_STOOQ_TICKER_SKIP_UNTIL: dict[str, float] = {}
_STOOQ_CONSECUTIVE_READ_TIMEOUTS = 0


def _mark_stooq_unreachable() -> None:
    global _STOOQ_UNREACHABLE_UNTIL
    _STOOQ_UNREACHABLE_UNTIL = monotonic() + STOOQ_UNREACHABLE_COOLDOWN_SECONDS


def _record_read_timeout(full_ticker: str) -> bool:
    """Skip ``full_ticker`` for a while; return True if the global cooldown started."""
    global _STOOQ_CONSECUTIVE_READ_TIMEOUTS
    now = monotonic()
    for key in [k for k, until in _STOOQ_TICKER_SKIP_UNTIL.items() if until <= now]:
        del _STOOQ_TICKER_SKIP_UNTIL[key]
    _STOOQ_TICKER_SKIP_UNTIL[full_ticker] = now + STOOQ_TICKER_SKIP_SECONDS
    _STOOQ_CONSECUTIVE_READ_TIMEOUTS += 1
    if _STOOQ_CONSECUTIVE_READ_TIMEOUTS < STOOQ_READ_TIMEOUTS_BEFORE_COOLDOWN:
        return False
    _STOOQ_CONSECUTIVE_READ_TIMEOUTS = 0
    _mark_stooq_unreachable()
    return True


def _record_stooq_responded() -> None:
    global _STOOQ_CONSECUTIVE_READ_TIMEOUTS
    _STOOQ_CONSECUTIVE_READ_TIMEOUTS = 0


def reset_stooq_unreachable_cooldown() -> None:
    """Clear the unreachable cooldown and per-ticker skips (used by tests)."""
    global _STOOQ_UNREACHABLE_UNTIL, _STOOQ_CONSECUTIVE_READ_TIMEOUTS
    _STOOQ_UNREACHABLE_UNTIL = 0.0
    _STOOQ_CONSECUTIVE_READ_TIMEOUTS = 0
    _STOOQ_TICKER_SKIP_UNTIL.clear()


def _handle_stooq_timeout(exc: Exception, full_ticker: str) -> pd.DataFrame:
    """Apply the per-ticker skip or global cooldown for a timeout/connection error."""
    if isinstance(exc, requests.exceptions.ReadTimeout):
        host_down = _record_read_timeout(full_ticker)
    else:
        _mark_stooq_unreachable()
        host_down = True
    if host_down:
        logger.warning(
            "Stooq request timed out or could not connect for %s (%s); skipping Stooq during cooldown",
            sanitise_log_value(full_ticker),
            sanitise_log_value(type(exc).__name__),
        )
    else:
        logger.warning(
            "Stooq read timed out for %s; skipping this ticker during cooldown",
            sanitise_log_value(full_ticker),
        )
    return pd.DataFrame(columns=STANDARD_COLUMNS)


def get_stooq_suffix(exchange: str) -> str:
    exchange_map = {
        "L": ".UK",
        "LSE": ".UK",
        "UK": ".UK",
        "LON": ".UK",
        "XLON": ".UK",
        "NASDAQ": ".US",
        "NYSE": ".US",
        "US": ".US",
        "AMEX": ".US",
        "XETRA": ".DE",
        "DE": ".DE",
        "F": ".F",
        "TO": ".TO",
        "TSX": ".TO",
    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unknown or unsupported exchange: '{exchange}'")
    return suffix


def format_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_stooq_timeseries_range(ticker: str, exchange: str, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch historical Stooq data using date range.
    """
    global STOOQ_DISABLED_UNTIL
    if date.today() <= STOOQ_DISABLED_UNTIL:
        raise StooqRateLimitError("Exceeded the daily hits limit")
    if not is_valid_ticker(ticker, exchange):
        logger.info(
            "Skipping Stooq fetch for unrecognized ticker %s.%s",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
        )
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    if monotonic() < _STOOQ_UNREACHABLE_UNTIL:
        raise StooqRateLimitError("Stooq unreachable; skipping during cooldown")
    suffix = get_stooq_suffix(exchange)
    full_ticker = ticker + suffix
    if monotonic() < _STOOQ_TICKER_SKIP_UNTIL.get(full_ticker, 0.0):
        raise StooqRateLimitError("Stooq timed out for this ticker; skipping during cooldown")

    logger.debug(
        "Preparing request for ticker=%s, exchange=%s, full_ticker=%s, start_date=%s, end_date=%s",
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
        sanitise_log_value(full_ticker),
        start_date,
        end_date,
    )

    params = {"s": full_ticker, "d1": format_date(start_date), "d2": format_date(end_date), "i": "d", "d": "d"}

    logger.debug("Fetching Stooq data with URL: %s and params: %s", BASE_URL, sanitise_log_value(params))
    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=config.stooq_timeout or 10,
        )
        _record_stooq_responded()
        if not response.ok:
            raise Exception(f"HTTP error {response.status_code} for {full_ticker}")

        if "Exceeded the daily hits limit" in response.text:
            logger.warning("Stooq: Exceeded the daily hits limit")
            STOOQ_DISABLED_UNTIL = date.today() + timedelta(days=1)
            raise StooqRateLimitError("Exceeded the daily hits limit")

        df = pd.read_csv(StringIO(response.text))
        if df.empty:
            raise RuntimeError("No data returned from Stooq")

        if "Date" not in df.columns or "Close" not in df.columns:
            raise ValueError(f"Unexpected format for {full_ticker}: columns = {df.columns.tolist()}")

        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df.sort_values("Date", inplace=True)
        df["Volume"] = df.get("Volume", None)
        df["Ticker"] = ticker

        logger.info("Fetched %d rows for %s", len(df), sanitise_log_value(full_ticker))

        df["Source"] = "Stooq"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        return _handle_stooq_timeout(exc, full_ticker)
    except Exception as e:
        logger.error("Failed to fetch Stooq data for %s: %s", sanitise_log_value(full_ticker), sanitise_log_value(e))
        raise


def fetch_stooq_timeseries(ticker: str, exchange: str, days: int = 365) -> pd.DataFrame:
    """
    Backward-compatible interface to fetch trailing days of data.
    """
    today = date.today()
    start = today - timedelta(days=days)
    logger.debug(
        "Fetching trailing %d days of data for %s on %s",
        days,
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
    )
    logger.debug(
        "Preparing request for ticker=%s, exchange=%s, start_date=%s, end_date=%s",
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
        start,
        today,
    )
    return fetch_stooq_timeseries_range(ticker, exchange, start, today)


if __name__ == "__main__":  # pragma: no cover
    # Example usage
    df = fetch_stooq_timeseries("GRG", "LSE", days=700)
    print(df.head())
