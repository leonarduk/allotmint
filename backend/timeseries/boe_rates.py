"""Bank of England market rates stored in the timeseries cache (#9322).

Daily Bank Rate and nominal par gilt yields from the BoE Interactive Database
(IADB), kept as one parquet per series under ``{timeseries_cache_base}/boe/``
(``boe/IUDBEDR.parquet`` etc.) with columns:

* ``Date``   -- datetime64[ms], one row per BoE publication day
* ``Value``  -- the published value (percent per annum for every series here)
* ``Series`` -- the IADB series code
* ``Units``  -- ``"percent"``
* ``Source`` -- ``"Bank of England IADB"``

Only :func:`refresh_boe_series` touches the network, and it runs from the
scheduled price refresh (``backend.common.prices.refresh_prices``). Readers
(:func:`load_boe_series`, :func:`load_boe_rates`) only read the stored files,
so MCP tools and page requests never call the BoE live.
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

BOE_IADB_CSV_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
BOE_SOURCE = "Bank of England IADB"
BOE_UNITS = "percent"
# The IADB rejects requests without a browser-like User-Agent.
_BOE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_BOE_TIMEOUT_SECONDS = 30
# First date fetched for a series with no stored file yet.
BOE_HISTORY_START = date(2007, 6, 1)

STORED_COLUMNS = ["Date", "Value", "Series", "Units", "Source"]


@dataclass(frozen=True)
class BoeSeries:
    """An IADB series this module stores."""

    code: str
    name: str
    tenor_years: int | None


BOE_SERIES: dict[str, BoeSeries] = {
    s.code: s
    for s in (
        BoeSeries("IUDBEDR", "Official Bank Rate", None),
        BoeSeries("IUDSNPY", "5-year nominal par gilt yield", 5),
        BoeSeries("IUDMNPY", "10-year nominal par gilt yield", 10),
        BoeSeries("IUDLNPY", "20-year nominal par gilt yield", 20),
    )
}


class BoeFetchError(RuntimeError):
    """The IADB returned something other than the expected CSV."""


def boe_series_path(code: str) -> str:
    """Where series ``code`` is stored (local path or S3 URI)."""
    return _ts_cache._cache_path("boe", f"{_known_code(code)}.parquet")


def _known_code(code: str) -> str:
    code = (code or "").strip().upper()
    if code not in BOE_SERIES:
        raise ValueError(f"Unknown Bank of England series code: {code!r}")
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
def fetch_boe_csv(codes: list[str], start: date, end: date) -> str:
    """Return the raw IADB CSV for ``codes`` over ``start``..``end`` (inclusive)."""
    params = {
        "csv.x": "yes",
        "Datefrom": start.strftime("%d/%b/%Y"),
        "Dateto": end.strftime("%d/%b/%Y"),
        "SeriesCodes": ",".join(codes),
        "CSVF": "TN",
        "UsingCodes": "Y",
        "VPD": "Y",
        "VFD": "N",
    }
    resp = requests.get(
        BOE_IADB_CSV_URL,
        params=params,
        headers={"User-Agent": _BOE_USER_AGENT},
        timeout=_BOE_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.text


def parse_boe_csv(text: str, codes: list[str]) -> dict[str, pd.DataFrame]:
    """Split an IADB CSV (``DATE`` then one column per code) into one stored-schema frame per code.

    Blank cells (non-publication days for that series) are dropped, so each
    frame only has days the series actually published.
    """
    try:
        raw = pd.read_csv(io.StringIO(text), dtype=str)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise BoeFetchError(f"Unparseable Bank of England CSV: {exc}") from exc
    missing = [c for c in ["DATE", *codes] if c not in raw.columns]
    if missing:
        raise BoeFetchError(f"Bank of England CSV is missing columns {missing}; got {list(raw.columns)[:6]}")
    dates = pd.to_datetime(raw["DATE"], format="%d %b %Y", errors="coerce").astype("datetime64[ms]")
    out: dict[str, pd.DataFrame] = {}
    for code in codes:
        values = pd.to_numeric(raw[code].str.strip(), errors="coerce")
        frame = pd.DataFrame({"Date": dates, "Value": values}).dropna()
        frame["Series"] = code
        frame["Units"] = BOE_UNITS
        frame["Source"] = BOE_SOURCE
        out[code] = frame.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    return out


# ──────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────
def _read_stored(code: str) -> pd.DataFrame:
    path = boe_series_path(code)
    try:
        stored = pd.read_parquet(path)
    except FileNotFoundError:
        return _empty_series()
    except Exception as exc:
        logger.warning("Unreadable BoE series file %s: %s", sanitise_log_value(path), sanitise_log_value(exc))
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
    path = boe_series_path(code)
    _ts_cache._ensure_local_dir(path)
    combined.to_parquet(path, index=False)
    return len(fetched)


def refresh_boe_series(codes: list[str] | None = None, *, today: date | None = None) -> dict[str, int]:
    """Fetch and append new BoE observations; return rows added per series code.

    One IADB request covers every requested series, starting the day after
    the earliest last-stored date (or :data:`BOE_HISTORY_START` for a series
    with no file). Each series then only appends dates after its own last
    stored date, so re-running is idempotent and existing rows are never
    rewritten. Raises :class:`BoeFetchError` / ``requests`` errors on a
    failed fetch, leaving the stored files untouched.
    """
    codes = [_known_code(c) for c in (codes or list(BOE_SERIES))]
    today = today or date.today()
    existing = {code: _read_stored(code) for code in codes}
    starts = [
        frame["Date"].max().date() + timedelta(days=1) if not frame.empty else BOE_HISTORY_START
        for frame in existing.values()
    ]
    start = min(starts)
    if start > today:
        return {code: 0 for code in codes}
    parsed = parse_boe_csv(fetch_boe_csv(codes, start, today), codes)
    added = {code: _append_new_dates(code, existing[code], parsed[code]) for code in codes}
    logger.info("Bank of England series refreshed from %s: %s", sanitise_log_value(start), sanitise_log_value(added))
    return added


# ──────────────────────────────────────────────────────────────
# Read (no network)
# ──────────────────────────────────────────────────────────────
def load_boe_series(code: str, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Stored observations of ``code`` between ``start`` and ``end`` (inclusive), without fetching.

    Returns the stored schema (``Date, Value, Series, Units, Source``); empty
    when the series has not been refreshed yet. Raises ``ValueError`` for a
    code not in :data:`BOE_SERIES`.
    """
    frame = _read_stored(code)
    if start is not None:
        frame = frame[frame["Date"] >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame["Date"] <= pd.Timestamp(end)]
    return frame.reset_index(drop=True)


def load_boe_rates(codes: list[str] | None = None, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Stored series as one wide frame: ``Date`` plus one column per code (percent), without fetching.

    Dates are the union of every series' publication days; a series with no
    value on a date is NaN there (e.g. gilt yields lag Bank Rate by a day).
    """
    codes = [_known_code(c) for c in (codes or list(BOE_SERIES))]
    wide = pd.DataFrame({"Date": pd.Series(dtype="datetime64[ms]")})
    for code in codes:
        series = load_boe_series(code, start, end)[["Date", "Value"]].rename(columns={"Value": code})
        wide = wide.merge(series, on="Date", how="outer")
    return wide.sort_values("Date").reset_index(drop=True)
