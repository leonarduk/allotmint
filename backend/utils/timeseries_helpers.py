import datetime
import json
import logging
import math
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from backend.common.currency import extract_currency
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.utils.html_render import render_timeseries_html

STANDARD_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]

logger = logging.getLogger(__name__)

# A pence/pounds (GBX/GBP) mix-up is always exactly 100x, so the only factors
# that make sense in ``scaling_overrides.json`` are 0.01 (pence -> pounds),
# 1 (no-op) and 100 (pounds -> pence). Anything else is almost certainly a
# typo -- e.g. ADM.L was once listed as 0.1, which rendered its prices 10x too
# high and, because downstream code only skips its own pence->GBP step when
# the factor equals the pence factor exactly, made the latest close 10x too
# low (3588p -> 358.8 -> 3.588 instead of 35.88) (#8597).
_VALID_OVERRIDE_FACTORS = (0.01, 1.0, 100.0)


def is_valid_override_factor(value: float) -> bool:
    """True if ``value`` is a pence/pounds unit factor (0.01, 1 or 100)."""
    return any(math.isclose(value, f, rel_tol=1e-9, abs_tol=1e-12) for f in _VALID_OVERRIDE_FACTORS)


def apply_scaling(df: pd.DataFrame, scale: float, scale_volume: bool = False) -> pd.DataFrame:
    if scale is None or scale == 1:
        return df
    df = df.copy()

    # Map lowercase -> actual column name
    name_map = {c.lower(): c for c in df.columns}

    for logical in ["open", "high", "low", "close"]:
        if logical in name_map:
            col = name_map[logical]
            df[col] = pd.to_numeric(df[col], errors="coerce") * scale

    if scale_volume and "volume" in name_map:
        col = name_map["volume"]
        df[col] = pd.to_numeric(df[col], errors="coerce") * scale

    return df


def _scaling_override_paths() -> list[Path]:
    """Return the ``scaling_overrides.json`` files to read, lowest priority first.

    The base table is ``<repo_root>/data/scaling_overrides.json``, or the copy
    bundled next to this package when there is no repo-root table. The
    configured data root (``DATA_ROOT``, e.g. ``../allotmint-data``) is the
    live dataset and is overlaid on top of the base, so it wins on conflicts
    while symbols only in the repo table (e.g. ``SGLN``) are kept. Previously
    the repo copy silently replaced the data-root table (#7787). Files that do
    not exist are skipped; the same file is never listed twice.
    """
    bundled = Path(__file__).resolve().parents[2] / "data" / "scaling_overrides.json"
    base = bundled
    configured_repo_root = getattr(config, "repo_root", None)
    if configured_repo_root:
        repo_copy = Path(str(configured_repo_root)).expanduser() / "data" / "scaling_overrides.json"
        if repo_copy.exists():
            base = repo_copy
    paths = [base] if base.exists() else []
    configured_data_root = getattr(config, "data_root", None)
    if configured_data_root:
        data_copy = Path(str(configured_data_root)).expanduser() / "scaling_overrides.json"
        if data_copy.exists() and all(data_copy.resolve() != p.resolve() for p in paths):
            paths.append(data_copy)
    return paths


def _load_scaling_overrides() -> tuple[dict, list[Path]]:
    """Load and merge the override tables from :func:`_scaling_override_paths`.

    Later files are overlaid section by section and symbol by symbol, so a
    ``DATA_ROOT`` entry replaces the repo entry for the same symbol without
    dropping the repo's other symbols. Section (exchange) keys are upper-cased
    so lookups are case-insensitive on the exchange. Unreadable or malformed
    files are skipped. Files are read on every call (no cache), so edits to
    either table take effect immediately.
    """
    merged: dict = {}
    sources: list[Path] = []
    for path in _scaling_override_paths():
        try:
            with path.open() as f:
                table = json.load(f)
        except Exception:
            continue
        if not isinstance(table, dict):
            continue
        sources.append(path)
        for ex_key, section in table.items():
            if not isinstance(section, dict):
                continue
            merged.setdefault(str(ex_key).upper(), {}).update(section)
    return merged, sources


def _infer_override_exchange(ticker: str, base: str, overrides: dict) -> str:
    """Best-effort exchange for a ``get_scaling_override`` call that passed none.

    Some callers pass no exchange (``routes/timeseries_meta`` passes ``""``),
    so an ``"L"`` override for the ticker would otherwise never match (#7787).
    An explicit suffix (``"ADM.L"``) is used only when the table has a section
    for that suffix which lists ``base`` -- a share-class suffix (``"BRK.B"``,
    ``"BF.B"``) must not be mistaken for an exchange. A padded LSE TIDM with a
    trailing dot (``"AV."``, ``"BP."``) has an *empty* suffix, so it never
    takes the suffix branch: it relies entirely on the fallback, which uses
    the single exchange section of the table that lists ``base``. If no
    section, or more than one, lists ``base`` the result is ``""``. The
    ``"*"`` section is never an inferred exchange; ``get_scaling_override``
    consults it separately. Section keys are compared upper-cased in both
    branches (``_load_scaling_overrides`` already normalises them).
    """
    if not isinstance(overrides, dict):
        return ""
    sections = {
        str(ex_key).upper(): table
        for ex_key, table in overrides.items()
        if str(ex_key) != "*" and isinstance(table, dict)
    }
    parts = re.split(r"[.:]", ticker, maxsplit=1)
    if len(parts) == 2 and parts[1]:
        suffix = parts[1].upper()
        if base in sections.get(suffix, {}):
            return suffix
    matches = [ex_key for ex_key, table in sections.items() if base in table]
    return matches[0] if len(matches) == 1 else ""


def get_scaling_override(ticker: str, exchange: str, requested_scaling: Optional[float]) -> float:
    """Return the factor to multiply a fetched OHLC/quote value by to get GBP.

    None of this app's free data sources (Stooq, FT, Yahoo's chart/quote
    endpoints, Alpha Vantage) reliably report whether an LSE ("L" exchange)
    price is quoted in pounds or pence -- Yahoo in particular returns raw
    pence for many LSE equities/ETFs/trusts with no distinguishing signal in
    the response. There is no generic way to auto-detect this from the fetch
    response alone, so it falls back to two curated sources of truth, in
    order:

    1. ``data/scaling_overrides.json`` -- an explicit ``{"<exchange>": {"<ticker
       base>": <factor>}}`` table (0.01 for pence). This is the primary,
       always-correct source once populated.
    2. The instrument's ``currency`` metadata via ``extract_currency`` --
       treated as pence only for the "GBX"/"GBp"-style codes.

    If a *new* LSE ticker's price renders ~100x too high (or too low), it
    almost always means neither source has caught up with that ticker's real
    quote convention yet -- add an entry to ``data/scaling_overrides.json``
    rather than guessing at a codewide fix; see #6845 for the investigation
    that established this is a per-ticker data gap, not a pipeline bug.
    """
    if requested_scaling is not None:
        return requested_scaling

    ov, sources = _load_scaling_overrides()
    path = ", ".join(str(src) for src in sources) or "<no scaling_overrides.json>"

    base = re.split(r"[.:]", ticker)[0].upper()
    ex = (exchange or "").upper() or _infer_override_exchange(ticker, base, ov)

    # Overrides are applied at read time only (callers do
    # ``apply_scaling(df, get_scaling_override(...))`` on series loaded from
    # the cache) and are never written back into cached series, so editing a
    # factor here or in scaling_overrides.json needs no cache backfill (#8597).
    #
    # Try: exact -> base -> per-exchange wildcard -> global wildcard. A factor
    # rejected by is_valid_override_factor falls through to the next candidate.
    candidates = [
        (ex, ticker),
        (ex, base),
        (ex, "*"),
        ("*", base),
        ("*", "*"),
    ]
    for ex_key, t_key in candidates:
        if ex_key in ov and t_key in ov[ex_key]:
            try:
                value = float(ov[ex_key][t_key])
            except Exception:
                continue
            if not is_valid_override_factor(value):
                logger.warning(
                    "Ignoring scaling override %s for %s/%s in %s: only 0.01, 1 or 100 are valid "
                    "pence/pounds factors; falling back to currency metadata",
                    sanitise_log_value(value),
                    sanitise_log_value(ex_key),
                    sanitise_log_value(t_key),
                    sanitise_log_value(path),
                )
                continue
            return value

    full = base if not ex else f"{base}.{ex}"
    currency = None

    try:  # Prefer instrument metadata when available
        from backend.common.instruments import get_instrument_meta  # type: ignore

        try:
            inst_meta = get_instrument_meta(full) or {}
            if not inst_meta and full != base:
                inst_meta = get_instrument_meta(base) or {}
        except Exception:
            inst_meta = {}
        currency = extract_currency(inst_meta)
    except Exception:
        currency = None

    if not currency:
        try:
            from backend.common import portfolio_utils  # type: ignore

            try:
                sec_meta = portfolio_utils.get_security_meta(full) or portfolio_utils.get_security_meta(base)
            except Exception:
                sec_meta = None
            currency = extract_currency(sec_meta)
        except Exception:
            currency = None

    if currency is not None:
        return currency.pence_factor
    return 1.0


def handle_timeseries_response(
    df: pd.DataFrame,
    format: str,
    title: str,
    subtitle: str,
    metadata: Optional[dict] = None,
):
    if df.empty:
        return HTMLResponse("<h1>No data found</h1>", status_code=404)

    if format == "json":
        payload = df.to_dict(orient="records")
        if metadata is not None:
            return JSONResponse(content={**metadata, "prices": payload})
        return JSONResponse(content=payload)
    elif format == "csv":
        return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")
    else:
        return render_timeseries_html(df, title, subtitle)


# ── new helper ──────────────────────────────────────────────
def _nearest_weekday(d: datetime.date, forward: bool) -> datetime.date:
    """
    Return *d* if it's a weekday; otherwise move to nearest weekday.

    forward=True  -> Friday->Mon (skip weekend forward)
    forward=False -> Saturday/Sunday->Fri (skip weekend backward)
    """
    while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        d += datetime.timedelta(days=1 if forward else -1)
    return d


def _is_isin(ticker: str) -> bool:
    base = re.split(r"[.:]", ticker)[0].upper()
    return len(base) == 12 and base.isalnum()


def resolve_date_range(
    days: int,
    *,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> Tuple[datetime.date, datetime.date]:
    """Resolve a ``(start_date, end_date)`` window for timeseries queries.

    If *start_date* and/or *end_date* are supplied explicitly they take
    precedence over the computed value for that bound.  When only *days* is
    given the defaults are:

    - ``end_date``   → yesterday (``today - 1 day``)
    - ``start_date`` → ``today - days``; ``date(1900, 1, 1)`` when
      ``days <= 0`` (meaning "all available history").

    When *end_date* is supplied but *start_date* is not, *start_date* is
    anchored relative to *end_date* (i.e. ``end_date - days``) rather than
    to today.  This lets callers specify a window ending at a historical date
    without having to compute both bounds themselves.

    ``days <= 0`` always maps to the "all history" sentinel
    ``date(1900, 1, 1)`` regardless of whether *end_date* is supplied.

    **Window-size semantics**: ``days`` means "calendar days back", so
    the resulting window spans ``days + 1`` inclusive days
    (e.g. ``days=2, end_date=2024-01-03`` → ``[2024-01-01, 2024-01-03]``).
    This is consistent with the original today-anchored path.

    Parameters
    ----------
    days:
        Lookback window in calendar days.  Only used when the corresponding
        explicit date is ``None``.
    start_date:
        Optional explicit start bound.  Overrides the ``days`` calculation.
    end_date:
        Optional explicit end bound.  Overrides the default yesterday anchor.

    Returns
    -------
    tuple[date, date]
        A ``(start_date, end_date)`` pair ready to pass to
        ``load_meta_timeseries_range`` or any other range-aware loader.
    """
    explicit_end = end_date is not None
    if end_date is None:
        end_date = datetime.date.today() - datetime.timedelta(days=1)
    if start_date is None:
        if days <= 0:
            # days=0/negative means "all available history" regardless of end_date
            start_date = datetime.date(1900, 1, 1)
        elif explicit_end:
            # end_date was explicitly supplied: anchor start relative to it.
            # Semantics: days=N means "N calendar days back", giving an inclusive
            # window of N+1 days — the same as the today-anchored path below.
            start_date = end_date - datetime.timedelta(days=days)
        else:
            # Neither date supplied: anchor to today to preserve original window
            start_date = datetime.date.today() - datetime.timedelta(days=days)
    return start_date, end_date


def apply_date_range(
    df: pd.DataFrame,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> pd.DataFrame:
    """Filter *df* to rows where the ``Date`` column falls in ``[start_date, end_date]``.

    Either bound may be ``None`` to leave that side open (true no-op for that bound).
    Handles both ``datetime64`` and plain ``date`` dtype in the ``Date`` column.

    Null handling: NaT (datetime64 columns) is converted to ``None`` via ``.dt.date``
    before filtering; ``None`` values in object-dtype columns are caught by
    ``dates.notna()``.  In both cases null rows are always dropped regardless of
    which bounds are supplied.  Note: pandas returns ``False`` (not ``TypeError``)
    when comparing ``None`` against a ``datetime.date`` in an object-dtype Series
    (verified on pandas ≥ 2.x / Python ≥ 3.10), so the ``notna()`` guard is a
    belt-and-suspenders safety measure rather than strictly necessary, but is kept
    for explicitness and forward-compatibility.

    Returns a new DataFrame with reset index; the original frame is not mutated.
    When ``df`` is empty or has no ``Date`` column a copy of ``df`` is returned
    (index is not reset in that case).

    Performance (#8127): for a ``datetime64`` column with no null values that is
    already sorted ascending — true of every per-ticker parquet history in the
    warm cache this is repeatedly called against (verified against the real
    cache: 171/171 files sorted, no NaT) — this uses ``Series.searchsorted`` to
    binary-search the two slice boundaries directly on the datetime64 values,
    an O(log n) lookup that also avoids the expensive ``.dt.date`` conversion
    (which builds a Python ``datetime.date`` object per row). Any column that
    is unsorted, contains nulls, is tz-aware, or is not ``datetime64`` falls
    back to the original O(n) boolean-mask scan below. ``start_date``/``end_date``
    are normalised to plain ``datetime.date`` up front (see below) before either
    path runs, so a caller passing a ``datetime``/``Timestamp``/``np.datetime64``/
    date-parseable string bound with a nonzero time component behaves
    identically on both paths — only the sorted-datetime64-no-nulls-tz-naive
    case gets the fast path, but the *result* is the same either way.
    """
    if df.empty or "Date" not in df.columns:
        return df.copy()
    # Normalise any date-like bound (datetime.date, datetime.datetime,
    # pd.Timestamp, np.datetime64, or a date-parseable string) to a plain
    # datetime.date up front, before either path below sees it. Without this,
    # a caller passing a bound with a nonzero time component would make the
    # fast path's pd.Timestamp(start_date)/pd.Timestamp(end_date) retain that
    # time and searchsorted against it, which can exclude rows earlier the
    # same calendar day that the date-truncated scan path would include --
    # the two paths must see the same bound type to actually be equivalent
    # (#8131 review). pd.Timestamp(...).normalize() handles every one of
    # those input types uniformly (a plain hasattr(x, "date") check misses
    # np.datetime64, which has no .date() method).
    if start_date is not None:
        start_date = pd.Timestamp(start_date).normalize().date()
    if end_date is not None:
        end_date = pd.Timestamp(end_date).normalize().date()
    dates = df["Date"]
    is_dt64 = pd.api.types.is_datetime64_any_dtype(dates)
    is_tz_naive = getattr(dates.dt, "tz", None) is None if is_dt64 else True
    # Fast path: _load_meta_parquet_cached marks frames it has verified as
    # sorted and null-free, letting us skip the O(n) hasnans/monotonic
    # checks that would otherwise make this helper still O(n) per call
    # (#8127). Only the cache module sets this attr; every other caller
    # takes the explicit-check branch below, preserving prior behavior.
    if df.attrs.get("_timeseries_date_sorted", False):
        fast_ok = is_dt64 and is_tz_naive
    else:
        fast_ok = is_dt64 and is_tz_naive and not dates.hasnans and dates.is_monotonic_increasing
    if fast_ok:
        lo = 0
        hi = len(dates)
        if start_date is not None:
            lo = int(dates.searchsorted(pd.Timestamp(start_date), side="left"))
        if end_date is not None:
            # Half-open upper bound: end_date is inclusive of the whole
            # calendar day, so anything strictly before the next day
            # qualifies — this also handles a Date column that carries a
            # nonzero time-of-day component, unlike truncating to `.dt.date`.
            hi = int(dates.searchsorted(pd.Timestamp(end_date) + pd.Timedelta(days=1), side="left"))
        return df.iloc[lo:hi].reset_index(drop=True).copy()
    # Normalise to plain date objects for comparison so that NaT (datetime64) and
    # None (object dtype) are both caught by isna() before the >= / <= tests.
    # For datetime64 columns .dt.date converts NaT → None; for object-dtype columns
    # the series is used as-is. Both cases are handled identically below.
    if is_dt64:
        dates = dates.dt.date
    # Drop NaT/None unconditionally — callers must not expect null rows to survive.
    mask = dates.notna()
    if start_date is not None:
        mask &= dates >= start_date
    if end_date is not None:
        mask &= dates <= end_date
    return df.loc[mask].reset_index(drop=True).copy()
