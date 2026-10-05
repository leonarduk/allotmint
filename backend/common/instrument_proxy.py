"""Instrument proxies: schema, validator and proxied history resolver (#9480).

An instrument's metadata (``<data_root>/instruments/<EX>/<SYM>.json``) may carry
an optional top-level ``proxy`` block saying which stored series stands in for
the instrument before its own price history starts::

    "proxy": {
      "daily": [
        {"ticker": "IGLT.L", "weight": 1.0, "currency": "GBP", "scale": 1.0, "from": null, "to": null}
      ],
      "long_history": [{"column": "uk_govt_bond_10y", "weight": 1.0}],
      "basis": "total_return",
      "rationale": "why this proxy was chosen",
      "reviewed": "2026-10-05"
    }

This schema is a contract shared with allotmint-data (which fills proxies in)
and allotmint-pro (which exposes them over MCP), so field names and meanings
must not change here alone.

Fields
------
``daily``
    Segments, each pointing at a series stored in ``timeseries/meta``
    (``ticker`` is ``SYMBOL.EXCHANGE``). ``weight`` is in (0, 1]. Segments with
    the same ``[from, to]`` window form one blend and their weights sum to 1
    (+/- 1e-6); different windows must not overlap. ``from``/``to`` are optional
    inclusive ISO dates, so one proxy can change units or currency partway
    through its history (e.g. EUR cents to 2009-01-01, GBP from 2009-01-02).
``scale`` (default 1)
    Multiplies the proxy close *after* the standard read-path scaling (see
    "Loader, scaling and currency" below). It is only for extra corrections;
    a GBX ticker already has its pence factor applied, so do not add 0.01.
``currency`` (default: the proxy instrument's metadata currency)
    Currency of the scaled close, converted to GBP with the stored FX history
    (``timeseries/fx/<CCY>.parquet``, ``Rate`` = GBP per unit). When it is
    defaulted from metadata, a pence code (GBX/GBp) counts as GBP because the
    read-path scaling already turned pence into pounds. An *explicit* pence
    code on a segment means the scaled close really is in pence and is
    multiplied by 0.01.
``long_history``
    Weighted columns of ``<data_root>/timeseries/long_history/annual_returns_gbp.csv``
    (decimal annual GBP total returns, one row per ``year``); weights sum to 1.
    Valid columns are :data:`LONG_HISTORY_COLUMNS`.
``basis``
    ``price`` or ``total_return``: what the daily proxy series measures.
``rationale``, ``reviewed``
    Required: free-text reason for the choice and the ISO date it was reviewed.

Either ``daily`` or ``long_history`` may be omitted, but not both. The
instrument's own unit scaling stays in ``scaling_overrides.json`` and is not
affected by a proxy.

Loader, scaling and currency
----------------------------
``backend.timeseries.cache.load_meta_timeseries_range`` returns the stored
``Close`` *exactly as cached* (the source's quote units, e.g. pence for many
LSE lines). It does **not** apply ``scaling_overrides.json``: every caller pairs
it with ``apply_scaling(df, get_scaling_override(ticker, exchange, None))``
(``backend/utils/timeseries_helpers.py``), whose fallback is the metadata
currency's pence factor. The loader's own FX step adds ``Close_gbp`` from the
*unscaled* ``Close`` and only for non-GBP/GBX instruments, so it is not used
here. This module therefore takes the raw ``Close``, applies the standard
override exactly once (the same pairing every other caller uses), then the
segment ``scale``, then converts the segment currency to GBP with
:func:`backend.timeseries.cache.load_fx_history`. All reads run inside
:func:`backend.timeseries.cache.cache_only`, so no price source is called.

Joining
-------
:func:`proxied_daily_history` uses the instrument's own GBP series from its
first date. Before that, blended proxy daily returns are chained backwards
from the first own close, so the stitched series meets it with no level jump.
Levels are never spliced: only returns are chained, so windows using
tickers at very different price levels join continuously. Each proxy ticker's
segments are first stitched into one GBP series, so a dated unit/currency
switch on one ticker stays continuous. At a boundary between windows that use
*different* tickers, the first day's return in the new window is computed
from that ticker's own last close before the window (converted with the new
segment's currency and scale); if it has no earlier close, the return comes
from the previous window's tickers instead. Rows stop at the first date no
window covers, or where no proxy has closes on both days. Missing or invalid
proxies leave the own series unchanged.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from backend.common.currency import CurrencyNormaliser
from backend.common.instruments import get_instrument_meta
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import cache_only, instrument_currency, load_fx_history, load_meta_timeseries_range
from backend.utils.timeseries_helpers import apply_scaling, get_scaling_override

logger = logging.getLogger(__name__)

LONG_HISTORY_COLUMNS = frozenset(
    {
        "uk_cash",
        "uk_govt_bond_10y",
        "uk_equity",
        "us_equity_gbp",
        "ex_us_dev_equity_gbp",
        "us_small_value_gbp",
        "gold_gbp",
    }
)
LONG_HISTORY_RELATIVE_PATH = Path("timeseries") / "long_history" / "annual_returns_gbp.csv"
VALID_BASES = frozenset({"price", "total_return"})
WEIGHT_TOLERANCE = 1e-6
OWN_SOURCE = "own"
OUTPUT_COLUMNS = ["Date", "Close_gbp", "Source"]

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3,4}$")


@dataclass(frozen=True)
class DailySegment:
    """One ``proxy.daily`` entry. ``from``/``to`` are named ``from_date``/``to_date``."""

    ticker: str
    weight: float
    currency: Optional[str] = None
    scale: float = 1.0
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    @property
    def window(self) -> tuple[Optional[date], Optional[date]]:
        return (self.from_date, self.to_date)

    def covers(self, day: date) -> bool:
        return (self.from_date is None or day >= self.from_date) and (self.to_date is None or day <= self.to_date)


@dataclass(frozen=True)
class LongHistoryComponent:
    """One ``proxy.long_history`` entry."""

    column: str
    weight: float


@dataclass(frozen=True)
class Proxy:
    """Parsed ``proxy`` block."""

    daily: tuple[DailySegment, ...]
    long_history: tuple[LongHistoryComponent, ...]
    basis: Optional[str]
    rationale: Optional[str]
    reviewed: Optional[date]

    def windows(self) -> list[tuple[Optional[date], Optional[date]]]:
        """Distinct ``[from, to]`` windows of the daily segments, in first-seen order."""
        return list(dict.fromkeys(seg.window for seg in self.daily))


# ──────────────────────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────────────────────
def _parse_iso_date(value: Any) -> Optional[date]:
    """``None`` for null; a ``date`` for an ISO string or date; ``ValueError`` otherwise."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise ValueError(f"not an ISO date: {value!r}")


def _parse_segment(raw: Mapping[str, Any]) -> DailySegment:
    scale = raw.get("scale")
    currency = raw.get("currency")
    return DailySegment(
        ticker=str(raw["ticker"]).strip().upper(),
        weight=float(raw["weight"]),
        currency=str(currency).strip() if currency else None,
        scale=1.0 if scale is None else float(scale),
        from_date=_parse_iso_date(raw.get("from")),
        to_date=_parse_iso_date(raw.get("to")),
    )


def parse_proxy(meta: Mapping[str, Any] | None) -> Proxy | None:
    """Typed view of ``meta["proxy"]``, or ``None`` when there is no proxy block.

    Raises ``ValueError``/``KeyError``/``TypeError`` on a malformed block; call
    :func:`validate_proxy` first when the metadata is untrusted.
    """
    raw = (meta or {}).get("proxy")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("proxy must be a JSON object")
    daily = tuple(_parse_segment(seg) for seg in raw.get("daily") or [])
    long_history = tuple(
        LongHistoryComponent(column=str(item["column"]).strip(), weight=float(item["weight"]))
        for item in raw.get("long_history") or []
    )
    rationale = raw.get("rationale")
    return Proxy(
        daily=daily,
        long_history=long_history,
        basis=raw.get("basis"),
        rationale=rationale.strip() if isinstance(rationale, str) else None,
        reviewed=_parse_iso_date(raw.get("reviewed")),
    )


# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────
def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_weight(value: Any, where: str) -> list[str]:
    if not _is_number(value):
        return [f"{where}: weight must be a number in (0, 1], got {value!r}"]
    if not 0 < value <= 1:
        return [f"{where}: weight {value} is outside (0, 1]"]
    return []


def _check_date_field(raw: Mapping[str, Any], key: str, where: str) -> list[str]:
    try:
        _parse_iso_date(raw.get(key))
    except (ValueError, TypeError):
        return [f"{where}: '{key}' is not an ISO date: {raw.get(key)!r}"]
    return []


def _check_ticker(value: Any, where: str, known: Optional[set[str]], own: Optional[str]) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{where}: ticker is missing"]
    ticker = value.strip().upper()
    sym, _, exch = ticker.rpartition(".")
    if not sym or not exch:
        return [f"{where}: ticker {value!r} must be SYMBOL.EXCHANGE"]
    if known is not None and ticker not in known:
        return [f"{where}: unknown ticker {ticker} (no stored series)"]
    if own and ticker == own:
        return [f"{where}: ticker {ticker} is the instrument itself"]
    return []


def _check_segment_fields(seg: Mapping[str, Any], where: str) -> list[str]:
    problems = _check_weight(seg.get("weight"), where)
    scale = seg.get("scale")
    if scale is not None and (not _is_number(scale) or scale <= 0):
        problems.append(f"{where}: scale must be a positive number, got {scale!r}")
    currency = seg.get("currency")
    if currency is not None and (not isinstance(currency, str) or not _CURRENCY_RE.match(currency.strip())):
        problems.append(f"{where}: currency must be a currency code, got {currency!r}")
    date_problems = _check_date_field(seg, "from", where) + _check_date_field(seg, "to", where)
    problems.extend(date_problems)
    if not date_problems:
        start, end = _parse_iso_date(seg.get("from")), _parse_iso_date(seg.get("to"))
        if start is not None and end is not None and start > end:
            problems.append(f"{where}: 'from' {start} is after 'to' {end}")
    return problems


def _windows_overlap(a: tuple[Optional[date], Optional[date]], b: tuple[Optional[date], Optional[date]]) -> bool:
    a_start, a_end = a[0] or date.min, a[1] or date.max
    b_start, b_end = b[0] or date.min, b[1] or date.max
    return a_start <= b_end and b_start <= a_end


def _check_blends(segments: list[DailySegment]) -> list[str]:
    """Weights per window sum to 1, no ticker repeats in a window, and windows don't overlap."""
    problems: list[str] = []
    windows = list(dict.fromkeys(seg.window for seg in segments))
    for window in windows:
        members = [seg for seg in segments if seg.window == window]
        label = _window_label(window)
        total = sum(seg.weight for seg in members)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            problems.append(f"proxy.daily window {label}: weights sum to {total:.6g}, expected 1")
        tickers = [seg.ticker for seg in members]
        for dup in sorted({t for t in tickers if tickers.count(t) > 1}):
            problems.append(f"proxy.daily window {label}: ticker {dup} appears more than once")
    for i, first in enumerate(windows):
        for second in windows[i + 1 :]:
            if _windows_overlap(first, second):
                problems.append(f"proxy.daily windows {_window_label(first)} and {_window_label(second)} overlap")
    return problems


def _window_label(window: tuple[Optional[date], Optional[date]]) -> str:
    start, end = window
    return f"[{start or 'start'}, {end or 'end'}]"


def _validate_daily(raw: Any, known: Optional[set[str]], own: Optional[str]) -> list[str]:
    if not isinstance(raw, list):
        return ["proxy.daily must be a list of segments"]
    problems: list[str] = []
    parsed: list[DailySegment] = []
    for i, seg in enumerate(raw):
        where = f"proxy.daily[{i}]"
        if not isinstance(seg, Mapping):
            problems.append(f"{where}: segment must be a JSON object")
            continue
        seg_problems = _check_ticker(seg.get("ticker"), where, known, own) + _check_segment_fields(seg, where)
        problems.extend(seg_problems)
        if not seg_problems:
            parsed.append(_parse_segment(seg))
    if parsed and len(parsed) == len(raw):
        problems.extend(_check_blends(parsed))
    return problems


def _validate_long_history(raw: Any, columns: frozenset[str] | set[str]) -> list[str]:
    if not isinstance(raw, list):
        return ["proxy.long_history must be a list of {column, weight} entries"]
    problems: list[str] = []
    seen: list[str] = []
    weights: list[float] = []
    for i, item in enumerate(raw):
        where = f"proxy.long_history[{i}]"
        if not isinstance(item, Mapping):
            problems.append(f"{where}: entry must be a JSON object")
            continue
        column = item.get("column")
        if not isinstance(column, str) or column.strip() not in columns:
            problems.append(f"{where}: unknown long-history column {column!r}")
        elif column.strip() in seen:
            problems.append(f"{where}: column {column.strip()} appears more than once")
        else:
            seen.append(column.strip())
        weight_problems = _check_weight(item.get("weight"), where)
        problems.extend(weight_problems)
        if not weight_problems:
            weights.append(float(item["weight"]))
    if not problems and abs(sum(weights) - 1.0) > WEIGHT_TOLERANCE:
        problems.append(f"proxy.long_history: weights sum to {sum(weights):.6g}, expected 1")
    return problems


def _validate_provenance(raw: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    basis = raw.get("basis")
    if basis is not None and basis not in VALID_BASES:
        problems.append(f"proxy.basis must be one of {sorted(VALID_BASES)}, got {basis!r}")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        problems.append("proxy.rationale is required")
    if raw.get("reviewed") is None:
        problems.append("proxy.reviewed is required (ISO date)")
    else:
        problems.extend(_check_date_field(raw, "reviewed", "proxy"))
    return problems


def validate_proxy(
    meta: Mapping[str, Any] | None,
    *,
    known_tickers: Optional[Iterable[str]] = None,
    long_history_columns: Optional[Iterable[str]] = None,
) -> list[str]:
    """Problems with ``meta["proxy"]``, one message per violation; ``[]`` when valid or absent.

    ``known_tickers`` (``SYMBOL.EXCHANGE``) enables the stored-series check;
    ``long_history_columns`` overrides :data:`LONG_HISTORY_COLUMNS`. Never
    raises on bad data.
    """
    if not isinstance(meta, Mapping):
        return []
    raw = meta.get("proxy")
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return ["proxy must be a JSON object"]
    known = {str(t).strip().upper() for t in known_tickers} if known_tickers is not None else None
    columns = frozenset(long_history_columns) if long_history_columns is not None else LONG_HISTORY_COLUMNS
    own = str(meta.get("ticker") or "").strip().upper() or None
    daily, long_history = raw.get("daily"), raw.get("long_history")
    problems: list[str] = []
    if not daily and not long_history:
        problems.append("proxy needs at least one of 'daily' or 'long_history'")
    if daily:
        problems.extend(_validate_daily(daily, known, own))
    if long_history:
        problems.extend(_validate_long_history(long_history, columns))
    problems.extend(_validate_provenance(raw))
    return problems


# ──────────────────────────────────────────────────────────────
# Price loading (GBP)
# ──────────────────────────────────────────────────────────────
def _split_ticker(ticker: str) -> tuple[str, str]:
    sym, _, exch = (ticker or "").strip().upper().rpartition(".")
    if not sym or not exch:
        raise ValueError(f"ticker must be SYMBOL.EXCHANGE, got {ticker!r}")
    return sym, exch


def _scaled_close(ticker: str, start: date, end: date) -> pd.Series:
    """Stored closes for ``ticker`` in ``[start, end]`` with the standard override applied once.

    Indexed by normalised ``Timestamp``. Rows outside the window (the
    cache-only loader's last-close fallback, or its weekend retry) are dropped.
    """
    sym, exch = _split_ticker(ticker)
    with cache_only():
        df = load_meta_timeseries_range(sym, exch, start, end)
    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    df = apply_scaling(df[["Date", "Close"]], get_scaling_override(sym, exch, None))
    dates = pd.to_datetime(df["Date"]).dt.normalize()
    close = pd.Series(pd.to_numeric(df["Close"], errors="coerce").to_numpy(), index=dates)
    in_window = (close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))
    close = close[in_window].dropna()
    return close[~close.index.duplicated(keep="last")].sort_index()


def _default_currency(ticker: str) -> str:
    """Metadata currency of ``ticker``; pence counts as GBP (the override already scaled it)."""
    sym, exch = _split_ticker(ticker)
    norm = CurrencyNormaliser.from_raw(instrument_currency(sym, exch))
    return "GBP" if norm.is_pence else norm.canonical


def _to_gbp(close: pd.Series, currency: str, *, ticker: str) -> pd.Series:
    """``close`` (in ``currency``) converted to GBP with stored FX; days with no rate yet are dropped."""
    norm = CurrencyNormaliser.from_raw(currency)
    if norm.is_pence:
        return close * norm.pence_factor
    if norm.canonical == "GBP" or close.empty:
        return close
    fx = load_fx_history(norm.canonical)
    if fx.empty:
        logger.warning(
            "No stored %s FX history; cannot convert %s to GBP",
            sanitise_log_value(norm.canonical),
            sanitise_log_value(ticker),
        )
        return pd.Series(dtype=float)
    rates = pd.Series(pd.to_numeric(fx["Rate"], errors="coerce").to_numpy(), index=pd.to_datetime(fx["Date"]))
    rates = rates.dropna().sort_index()
    aligned = rates.reindex(rates.index.union(close.index)).ffill().reindex(close.index)
    if aligned.isna().any():
        logger.warning(
            "Dropping %s %s closes before the first stored %s rate",
            sanitise_log_value(int(aligned.isna().sum())),
            sanitise_log_value(ticker),
            sanitise_log_value(norm.canonical),
        )
    return (close * aligned).dropna()


def _own_gbp_series(ticker: str, start: date, end: date) -> pd.Series:
    return _to_gbp(_scaled_close(ticker, start, end), _default_currency(ticker), ticker=ticker)


def _segment_mask(raw: pd.Series, seg: DailySegment, others: list[DailySegment]) -> list[bool]:
    """Dates of ``raw`` converted by ``seg``: its window, plus the last close before it.

    The extra prior close lets the first day of a window have a return when
    the previous window used a different ticker. It is skipped when another
    segment of the same ticker covers that date (a dated unit/currency switch),
    which already converts it in its own units.
    """
    mask = [seg.covers(ts.date()) for ts in raw.index]
    if seg.from_date is not None:
        before = [i for i, ts in enumerate(raw.index) if ts.date() < seg.from_date]
        if before and not any(o.covers(raw.index[before[-1]].date()) for o in others):
            mask[before[-1]] = True
    return mask


def _proxy_ticker_series(ticker: str, segments: list[DailySegment], start: date, end: date) -> pd.Series:
    """One GBP series for ``ticker``, each date converted by the segment whose window covers it."""
    raw = _scaled_close(ticker, start, end)
    if raw.empty:
        logger.warning(
            "Proxy series %s has no stored prices in %s..%s",
            sanitise_log_value(ticker),
            sanitise_log_value(start),
            sanitise_log_value(end),
        )
        return raw
    parts = []
    for seg in segments:
        mask = _segment_mask(raw, seg, [o for o in segments if o is not seg])
        if any(mask):
            currency = seg.currency or _default_currency(ticker)
            parts.append(_to_gbp(raw[mask] * seg.scale, currency, ticker=ticker))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts).sort_index()


# ──────────────────────────────────────────────────────────────
# Backward chaining
# ──────────────────────────────────────────────────────────────
def _window_members(proxy: Proxy, day: date) -> Optional[list[DailySegment]]:
    members = [seg for seg in proxy.daily if seg.covers(day)]
    return members or None


def _blended_return(prev: pd.Series, curr: pd.Series, members: list[DailySegment]) -> Optional[float]:
    """Weighted ``curr/prev - 1`` across ``members``; weights renormalised over tickers with both values."""
    total_weight = 0.0
    weighted = 0.0
    for seg in members:
        p0, p1 = prev.get(seg.ticker), curr.get(seg.ticker)
        if p0 is None or p1 is None or pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            continue
        weighted += seg.weight * (p1 / p0 - 1.0)
        total_weight += seg.weight
    return weighted / total_weight if total_weight > 0 else None


def _source_label(members: list[DailySegment]) -> str:
    return "proxy:" + "+".join(seg.ticker for seg in members)


def _level_row(levels: pd.DataFrame, day: pd.Timestamp) -> pd.Series:
    """Row of ``levels`` for ``day`` as a ``Series`` (ticker -> GBP level).

    ``levels`` is indexed by a de-duplicated grid (built from a ``set``), so a
    scalar ``.loc`` lookup always yields one row; a ``DataFrame`` here would
    mean that invariant was broken.
    """
    row = levels.loc[day]
    if not isinstance(row, pd.Series):
        raise TypeError(f"levels index has duplicate entries for {day}")
    return row


def _step_back(proxy: Proxy, levels: pd.DataFrame, d_prev: pd.Timestamp, d_next: pd.Timestamp):
    """``(return d_prev->d_next, members used)``, or ``None`` when no proxy covers the step.

    The window covering ``d_next`` is tried first. Only when its tickers have
    no close on ``d_prev`` (a new ticker with no earlier history) does it fall
    back to the window covering ``d_prev``.
    """
    candidates = (_window_members(proxy, d_next.date()), _window_members(proxy, d_prev.date()))
    for members in candidates:
        if members is None:
            continue
        ret = _blended_return(_level_row(levels, d_prev), _level_row(levels, d_next), members)
        if ret is not None and ret > -1.0:
            return ret, members
    return None


def _chain_backwards(proxy: Proxy, series: dict[str, pd.Series], anchor: pd.Timestamp, level: float) -> pd.DataFrame:
    """Proxy rows before ``anchor``, rebased so chaining their returns forward reaches ``level``."""
    frames = {t: s[s.index <= anchor] for t, s in series.items() if not s.empty}
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    grid = sorted(set().union(*(s.index for s in frames.values())) | {anchor})
    levels = pd.DataFrame(frames).reindex(grid).ffill()
    rows: list[tuple[pd.Timestamp, float, str]] = []
    for i in range(len(grid) - 1, 0, -1):
        prev_members = _window_members(proxy, grid[i - 1].date())
        if prev_members is None:
            break  # outside every window
        step = _step_back(proxy, levels, grid[i - 1], grid[i])
        if step is None:
            break  # no proxy close on both days
        level = level / (1.0 + step[0])
        rows.append((grid[i - 1], level, _source_label(prev_members)))
    rows.reverse()
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


# ──────────────────────────────────────────────────────────────
# Public resolvers
# ──────────────────────────────────────────────────────────────
def _own_frame(own: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Date": own.index, "Close_gbp": own.to_numpy(dtype=float), "Source": OWN_SOURCE})


def _usable_proxy(ticker: str, meta: Mapping[str, Any]) -> Proxy | None:
    """The parsed proxy when it is present and valid; logs and returns ``None`` otherwise."""
    problems = validate_proxy(meta)
    if problems:
        logger.warning(
            "Ignoring invalid proxy for %s: %s", sanitise_log_value(ticker), sanitise_log_value("; ".join(problems))
        )
        return None
    return parse_proxy(meta)


def _trim(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    dates = pd.to_datetime(frame["Date"])
    keep = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    out = frame.loc[keep].reset_index(drop=True)
    out["Date"] = pd.to_datetime(out["Date"])
    return out[OUTPUT_COLUMNS]


def proxied_daily_history(ticker: str, start: date, end: date) -> pd.DataFrame:
    """GBP daily closes for ``ticker`` over ``[start, end]``, proxied before its own history.

    Columns ``Date, Close_gbp, Source`` (``own`` or ``proxy:<T1>[+<T2>...]``).
    Without a valid ``proxy.daily`` block this is just the own GBP series.
    With no own history at all there is nothing to anchor a proxy to, so the
    result is empty (and a warning is logged).
    """
    canonical = (ticker or "").strip().upper()
    own = _own_gbp_series(canonical, start, max(end, date.today()))
    if own.empty:
        logger.warning("No own price history for %s; cannot build a proxied history", sanitise_log_value(canonical))
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    own_frame = _own_frame(own)
    first_own = own.index[0]
    proxy = _usable_proxy(canonical, get_instrument_meta(canonical))
    if proxy is None or not proxy.daily or first_own.date() <= start:
        return _trim(own_frame, start, end)
    tickers = list(dict.fromkeys(seg.ticker for seg in proxy.daily))
    series = {
        t: _proxy_ticker_series(t, [s for s in proxy.daily if s.ticker == t], start, first_own.date()) for t in tickers
    }
    proxied = _chain_backwards(proxy, series, first_own, float(own.iloc[0]))
    if proxied.empty:
        return _trim(own_frame, start, end)
    return _trim(pd.concat([proxied, own_frame], ignore_index=True), start, end)


def _long_history_csv() -> Optional[Path]:
    root = getattr(config, "data_root", None)
    return Path(root) / LONG_HISTORY_RELATIVE_PATH if root else None


def long_history_annual(ticker: str) -> pd.Series:
    """Weighted annual GBP returns for ``ticker`` from its ``proxy.long_history`` mapping.

    Indexed by ``year`` (int), values are decimal returns. Years where any
    weighted column is blank are dropped rather than reweighted. Returns an
    empty series (and logs why) when there is no valid mapping or the CSV is
    missing or lacks a column.
    """
    canonical = (ticker or "").strip().upper()
    empty = pd.Series(dtype=float, name="return_gbp").rename_axis("year")
    proxy = _usable_proxy(canonical, get_instrument_meta(canonical))
    if proxy is None or not proxy.long_history:
        logger.info("No long-history proxy mapping for %s", sanitise_log_value(canonical))
        return empty
    path = _long_history_csv()
    if path is None or not path.is_file():
        logger.warning(
            "Long-history returns CSV not found at %s; no long-run returns for %s",
            sanitise_log_value(str(path)),
            sanitise_log_value(canonical),
        )
        return empty
    try:
        table = pd.read_csv(path)
    except (OSError, ValueError) as exc:  # pandas' ParserError/EmptyDataError are ValueErrors
        logger.warning("Cannot read long-history CSV %s: %s", sanitise_log_value(str(path)), sanitise_log_value(exc))
        return empty
    columns = [c.column for c in proxy.long_history]
    missing = [c for c in ["year", *columns] if c not in table.columns]
    if missing:
        logger.warning(
            "Long-history CSV %s lacks columns %s", sanitise_log_value(str(path)), sanitise_log_value(missing)
        )
        return empty
    table = table[["year", *columns]].apply(pd.to_numeric, errors="coerce").dropna()
    weights = pd.Series({c.column: c.weight for c in proxy.long_history})
    weighted = (table[columns] * weights[columns]).sum(axis=1)
    weighted.index = pd.Index(table["year"].astype(int), name="year")
    return weighted.rename("return_gbp")
