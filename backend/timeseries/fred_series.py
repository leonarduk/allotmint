"""FRED corporate credit-spread series stored in the timeseries cache (#10602).

Daily spreads from FRED (Federal Reserve Bank of St. Louis), kept as one
parquet per series under ``{timeseries_cache_base}/fred/``
(``fred/BAA10Y.parquet`` etc.) with the same schema as
:mod:`backend.timeseries.boe_rates`:

* ``Date``   -- datetime64[ms], one row per FRED observation day
* ``Value``  -- the published value (percentage points for every series here)
* ``Series`` -- the FRED series code
* ``Units``  -- ``"percent"``
* ``Source`` -- ``"FRED"``

Only :func:`refresh_fred_series` touches the network, and it runs from the
scheduled price refresh (``backend.common.prices.refresh_prices``). Readers
(:func:`load_fred_series`, :func:`load_fred_rates`) only read the stored
files, so MCP tools and page requests never call FRED live.

Licensing: the Moody's and ICE BofA series are copyrighted by those
providers and redistributed by FRED under their terms (ICE's for personal,
non-commercial use). They are stored in the data root only and never
committed to the repo.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import requests

from backend.logging_setup import sanitise_log_value
from backend.timeseries import cache as _ts_cache

logger = logging.getLogger(__name__)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SOURCE = "FRED"
FRED_UNITS = "percent"
# No User-Agent header on purpose: with a browser UA the request hung, while
# the default one returns at once.
_FRED_TIMEOUT_SECONDS = 30
# Date column of the CSV: ``observation_date`` today, ``DATE`` in older exports.
_DATE_COLUMNS = ("observation_date", "DATE")

STORED_COLUMNS = ["Date", "Value", "Series", "Units", "Source"]


@dataclass(frozen=True)
class FredSeries:
    """A FRED series this module stores."""

    code: str
    name: str


FRED_SERIES: dict[str, FredSeries] = {
    s.code: s
    for s in (
        FredSeries("BAA10Y", "Moody's Baa corporate bond yield minus 10-year Treasury"),
        FredSeries("AAA10Y", "Moody's Aaa corporate bond yield minus 10-year Treasury"),
        FredSeries("BAMLH0A0HYM2", "ICE BofA US High Yield Index option-adjusted spread"),
        FredSeries("BAMLC0A0CM", "ICE BofA US Corporate Index option-adjusted spread"),
        FredSeries("BAMLHE00EHYIOAS", "ICE BofA Euro High Yield Index option-adjusted spread"),
    )
}


class FredFetchError(RuntimeError):
    """FRED returned something other than the expected CSV."""


def fred_series_path(code: str) -> str:
    """Where series ``code`` is stored (local path or S3 URI)."""
    return _ts_cache._cache_path("fred", f"{_known_code(code)}.parquet")


def _known_code(code: str) -> str:
    code = (code or "").strip().upper()
    if code not in FRED_SERIES:
        raise ValueError(f"Unknown FRED series code: {code!r}")
    return code


def _empty_series() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.Series(dtype="datetime64[ms]"),
            "Value": pd.Series(dtype="float64"),
            "Series": pd.Series(dtype="object"),
            "Units": pd.Series(dtype="object"),
            "Source": pd.Series(dtype="object"),
        }
    )


# ──────────────────────────────────────────────────────────────
# Fetch + normalise
# ──────────────────────────────────────────────────────────────
def fetch_fred_csv(code: str, start: date | None = None) -> str:
    """Return the raw FRED CSV for ``code`` from ``start`` (or its full history when ``None``)."""
    params = {"id": code}
    if start is not None:
        params["cosd"] = start.isoformat()
    resp = requests.get(FRED_CSV_URL, params=params, timeout=_FRED_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.text


def parse_fred_csv(text: str, code: str) -> pd.DataFrame:
    """Normalise a FRED CSV (date column then ``code``) into the stored schema.

    Missing observations (``.`` or blank cells, e.g. US holidays) are dropped,
    so the frame only has days the series actually published.
    """
    try:
        raw = pd.read_csv(io.StringIO(text), dtype=str)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise FredFetchError(f"Unparseable FRED CSV for {code}: {exc}") from exc
    date_column = next((c for c in _DATE_COLUMNS if c in raw.columns), None)
    if date_column is None or code not in raw.columns:
        raise FredFetchError(f"FRED CSV for {code} is missing columns; got {list(raw.columns)[:6]}")
    dates = pd.to_datetime(raw[date_column], format="%Y-%m-%d", errors="coerce").astype("datetime64[ms]")
    values = pd.to_numeric(raw[code].str.strip(), errors="coerce")
    frame = pd.DataFrame({"Date": dates, "Value": values}).dropna()
    frame["Series"] = code
    frame["Units"] = FRED_UNITS
    frame["Source"] = FRED_SOURCE
    return frame.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────
def _read_stored(code: str) -> pd.DataFrame:
    path = fred_series_path(code)
    try:
        stored = pd.read_parquet(path)
    except FileNotFoundError:
        return _empty_series()
    except Exception as exc:
        logger.warning("Unreadable FRED series file %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
        return _empty_series()
    stored["Date"] = pd.to_datetime(stored["Date"]).astype("datetime64[ms]")
    stored["Value"] = pd.to_numeric(stored["Value"], errors="coerce")
    return stored.dropna(subset=["Value"]).sort_values("Date").reset_index(drop=True)[STORED_COLUMNS]


def _append_new_dates(code: str, existing: pd.DataFrame, fetched: pd.DataFrame) -> int:
    """Append rows of ``fetched`` dated after ``existing``'s last date; return how many were written."""
    if not existing.empty:
        fetched = fetched[fetched["Date"] > existing["Date"].max()]
    if fetched.empty:
        return 0
    frames = [f for f in (existing, fetched[STORED_COLUMNS]) if not f.empty]
    combined = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)
    path = fred_series_path(code)
    _ts_cache._ensure_local_dir(path)
    combined.to_parquet(path, index=False)
    return len(fetched)


def _refresh_one(code: str, today: date) -> int:
    """Fetch and append new observations of one series; return rows added."""
    existing = _read_stored(code)
    start = existing["Date"].max().date() + timedelta(days=1) if not existing.empty else None
    if start is not None and start > today:
        return 0
    return _append_new_dates(code, existing, parse_fred_csv(fetch_fred_csv(code, start), code))


def refresh_fred_series(codes: list[str] | None = None, *, today: date | None = None) -> dict[str, int]:
    """Fetch and append new FRED observations; return rows added per refreshed series code.

    Each series is one request: its full history when it has no stored file,
    otherwise from the day after its last stored date. Only later dates are
    appended, so re-running is idempotent and existing rows are never
    rewritten. A series whose fetch fails is logged and left untouched while
    the others still refresh; :class:`FredFetchError` is raised only when
    every requested series failed.
    """
    codes = [_known_code(c) for c in (codes or list(FRED_SERIES))]
    today = today or date.today()
    added: dict[str, int] = {}
    failures: dict[str, str] = {}
    for code in codes:
        try:
            added[code] = _refresh_one(code, today)
        except (requests.RequestException, FredFetchError) as exc:
            failures[code] = str(exc)
            logger.warning("FRED series %s refresh failed: %s", sanitise_log_value(code), sanitise_log_value(exc))
    if failures and not added:
        raise FredFetchError(f"Every FRED series refresh failed: {failures}")
    logger.info("FRED series refreshed: %s", sanitise_log_value(added))
    return added


# ──────────────────────────────────────────────────────────────
# Read (no network)
# ──────────────────────────────────────────────────────────────
def load_fred_series(code: str, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Stored observations of ``code`` between ``start`` and ``end`` (inclusive), without fetching.

    Returns the stored schema (``Date, Value, Series, Units, Source``); empty
    when the series has not been refreshed yet. Raises ``ValueError`` for a
    code not in :data:`FRED_SERIES`.
    """
    frame = _read_stored(code)
    if start is not None:
        frame = frame[frame["Date"] >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame["Date"] <= pd.Timestamp(end)]
    return frame.reset_index(drop=True)


def load_fred_rates(codes: list[str] | None = None, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Stored series as one wide frame: ``Date`` plus one column per code (percent), without fetching.

    Dates are the union of every series' observation days; a series with no
    value on a date (or before its history starts) is NaN there.
    """
    codes = [_known_code(c) for c in (codes or list(FRED_SERIES))]
    wide = pd.DataFrame({"Date": pd.Series(dtype="datetime64[ms]")})
    for code in codes:
        series = load_fred_series(code, start, end)[["Date", "Value"]].rename(columns={"Value": code})
        wide = wide.merge(series, on="Date", how="outer")
    return wide.sort_values("Date").reset_index(drop=True)
