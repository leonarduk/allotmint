"""Read-only price-scale heuristics for the Data Quality engine (#7789, #8602).

A pence/pounds (GBX/GBP) mix-up or a wrong ``scaling_overrides.json`` factor
silently overstates a holding by 10x or 100x. That cannot be detected from a
fetch response alone (see ``get_scaling_override``), but it is detectable
after the fact from data already on disk:

* a step change between consecutive closes of ~10x / ~100x (or the inverse),
* a latest close far from the series' own trailing median, and
* an LSE equity or investment trust whose effective GBP price (raw close x
  scaling factor) is above anything plausible for that instrument type.

Separately, a day-on-day move above a (configurable) threshold that is not a
power-of-ten step is reported as a lower-severity signal: bad ticks and
mis-adjusted splits.

Pure functions over a DataFrame already loaded from the cache; nothing here
mutates the input or touches storage.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, TypedDict

import pandas as pd

# A consecutive-close ratio within this distance (in log10 units) of a
# non-zero power of ten is a scale step: 0.1 accepts 10x +/- ~26%.
SCALE_STEP_LOG10_TOLERANCE = 0.1
# Latest close vs the median of the preceding window.
TRAILING_MEDIAN_WINDOW = 30
TRAILING_MEDIAN_FACTOR = 20.0
# Default |day-on-day move| reported as LARGE_DAILY_MOVE (0.5 = 50%).
DEFAULT_LARGE_MOVE_THRESHOLD = 0.5
# Highest plausible per-share GBP price for an LSE instrument type. GBP-quoted
# ETFs legitimately trade at ~GBP 100-300, so they are deliberately absent.
# Equity headroom: Flutter (~GBP 208) and Games Workshop (~GBP 166) are the
# dearest correctly priced UK shares in the dataset; Aviva quoted in pence as
# pounds showed as GBP 726. Investment trusts rarely trade above ~GBP 40, while
# HICL quoted in pence as pounds showed as GBP 134.
PLAUSIBLE_MAX_GBP_PRICE = {
    "equity": 300.0,
    "investment trust": 75.0,
}
_MAX_REPORTED_POINTS = 10
_PENCE_FACTOR = 0.01
_VALID_FACTORS = (0.01, 1.0, 100.0)


class PriceStep(TypedDict):
    date: str
    previous: float
    value: float
    ratio: float


def close_series(df: pd.DataFrame) -> pd.Series:
    """Positive closes indexed by ISO date, sorted, one row per date (last wins)."""
    if df is None or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(df["Date"], errors="coerce").dt.date,
            "Close": pd.to_numeric(df["Close"], errors="coerce"),
        }
    ).dropna()
    frame = frame[frame["Close"] > 0].sort_values("Date", kind="stable")
    frame = frame.drop_duplicates(subset="Date", keep="last")
    return pd.Series(frame["Close"].to_numpy(dtype=float), index=[d.isoformat() for d in frame["Date"]])


def _steps(closes: pd.Series) -> Iterable[PriceStep]:
    previous = closes.shift(1)
    for day, prev, value in zip(closes.index[1:], previous.iloc[1:], closes.iloc[1:]):
        yield PriceStep(date=str(day), previous=float(prev), value=float(value), ratio=float(value / prev))


def is_scale_step(ratio: float, tolerance: float = SCALE_STEP_LOG10_TOLERANCE) -> bool:
    """True if ``ratio`` is close to 10**k for some k != 0."""
    if ratio <= 0 or not math.isfinite(ratio):
        return False
    exponent = math.log10(ratio)
    nearest = round(exponent)
    return nearest != 0 and abs(exponent - nearest) <= tolerance


def find_scale_steps(closes: pd.Series, *, exclude_dates: frozenset[str] = frozenset()) -> list[PriceStep]:
    """Consecutive-close steps of ~10x/100x/... (either direction)."""
    return [s for s in _steps(closes) if s["date"] not in exclude_dates and is_scale_step(s["ratio"])]


def find_large_moves(
    closes: pd.Series,
    threshold: float = DEFAULT_LARGE_MOVE_THRESHOLD,
    *,
    exclude_dates: frozenset[str] = frozenset(),
) -> list[PriceStep]:
    """Day-on-day moves with ``|ratio - 1| > threshold`` that are not scale steps."""
    return [
        s
        for s in _steps(closes)
        if s["date"] not in exclude_dates and abs(s["ratio"] - 1.0) > threshold and not is_scale_step(s["ratio"])
    ]


def trailing_median_ratio(closes: pd.Series, window: int = TRAILING_MEDIAN_WINDOW) -> float | None:
    """Latest close divided by the median of the ``window`` closes before it."""
    if len(closes) < 2:
        return None
    median = float(closes.iloc[-window - 1 : -1].median())
    return float(closes.iloc[-1]) / median if median > 0 else None


def instrument_type(meta: dict[str, Any] | None) -> str:
    meta = meta or {}
    return str(meta.get("instrument_type") or meta.get("instrumentType") or "").strip().lower()


def plausible_max_gbp_price(exchange: str, meta: dict[str, Any] | None) -> float | None:
    """Price ceiling for an LSE equity / investment trust; None when not gated."""
    if exchange.upper() != "L":
        return None
    return PLAUSIBLE_MAX_GBP_PRICE.get(instrument_type(meta))


def suggested_override_factor(current_scale: float) -> float | None:
    """The scaling_overrides.json factor that would divide the price by 100, if valid."""
    candidate = current_scale * _PENCE_FACTOR
    for factor in _VALID_FACTORS:
        if math.isclose(candidate, factor, rel_tol=1e-9):
            return factor
    return None


def limit_points(steps: list[PriceStep]) -> list[PriceStep]:
    """Most recent points only, so an issue preview stays small."""
    return steps[-_MAX_REPORTED_POINTS:]
