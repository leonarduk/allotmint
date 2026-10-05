"""Re-base cached meta timeseries onto traded prices and backfill dividends (#9340).

Until #9340 the Yahoo fetcher stored dividend-adjusted closes, adjusted as
of each fetch. The rolling cache only re-fetches an overlap window, so a
long-lived series became a patchwork of adjustment dates: ``stored / raw``
is constant within each fetch's rows and steps at every overlap edge
(VHYL.L: 0.9793, 0.9848, 0.9898, 1.0000, 0.9944, 1.0000 across 2025-26).

For each ``<SYMBOL>_<EXCHANGE>.parquet`` this re-fetches the stored date
range from Yahoo on the traded basis (``auto_adjust=False``: split-adjusted,
not dividend-adjusted) together with its dividends and splits, and reports:

* ``max|s/r-1|`` - the largest ``stored / raw - 1`` on shared dates;
* ``segments``   - runs of dates with a constant ``stored / raw`` (one, with
  ``max|s/r-1|`` ~0, means the file is already raw). A series adjusted once
  steps at every ex-date, so ``stray`` counts only the steps with no
  dividend or split since the previous segment: the fabricated moves at
  overlap-window edges (or bad rows);
* ``change``     - stored rows whose Close differs from raw by more than
  rounding, ``refine`` - rows that differ by less (a stored close rounded to
  2 dp before #9369 that the re-fetch now has at full precision), ``add`` -
  raw dates the file lacks, ``drop`` - stored dates Yahoo no longer has whose
  nearest ratio is off the raw basis;
* ``divs``/``splits`` - events found for the corporate-actions store.

Dry-run by default. ``--apply`` rewrites each meta file with the raw rows
(keeping stored dates Yahoo lacks only when they are already on the raw
basis) and merges the events into ``<root>/corporate_actions/``.

    python -m scripts.repair_dividend_basis_timeseries ../allotmint-data/timeseries/meta --ticker VHYL_L --segments
    python -m scripts.repair_dividend_basis_timeseries DIR --apply
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from backend.timeseries.corporate_actions import DIVIDEND, SPLIT, empty_actions, record_corporate_actions

logger = logging.getLogger(__name__)

# Stored rows written before #9369 are rounded to 2 dp (the re-fetch keeps six
# significant figures), so a ratio can wobble by ~0.01 / price.
RATIO_NOISE_FLOOR = 0.001
ROUNDING = 0.01
# A stored date Yahoo no longer returns is kept only if its nearest ratio is this close to 1.
KEEP_TOLERANCE = 0.002
CLOSE_CHANGE = 0.0051
# Closes this close (relative) are the same value; anything further apart but
# within CLOSE_CHANGE is a precision refinement, which ``--apply`` also writes.
SAME_CLOSE_RTOL = 1e-9

Fetcher = Callable[[str, str, pd.Timestamp, pd.Timestamp], tuple[pd.DataFrame, pd.DataFrame]]


@dataclass
class Segment:
    start: pd.Timestamp
    end: pd.Timestamp
    rows: int
    ratio: float


@dataclass
class Rebase:
    path: Path
    rows: int
    shared: int = 0
    max_dev: float = 0.0
    segments: list[Segment] = field(default_factory=list)
    stray: int = 0
    changed: int = 0
    refined: int = 0
    added: int = 0
    dropped: int = 0
    dividends: int = 0
    splits: int = 0
    error: str = ""
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    actions: pd.DataFrame = field(default_factory=empty_actions)


def _by_day(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize().astype("datetime64[ms]")
    return out.drop_duplicates("Date", keep="last").sort_values("Date").set_index("Date")


def ratio_series(stored: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """``stored / raw`` Close on shared dates, and the raw closes there."""
    s = pd.to_numeric(_by_day(stored)["Close"], errors="coerce")
    r = pd.to_numeric(_by_day(raw)["Close"], errors="coerce")
    shared = s.index.intersection(r.index)
    s, r = s[shared], r[shared]
    valid = s.notna() & r.notna() & (s > 0) & (r > 0)
    return (s[valid] / r[valid]).sort_index(), r[valid].sort_index()


def basis_segments(ratios: pd.Series, raw_closes: pd.Series) -> list[Segment]:
    """Split ``ratios`` into runs whose ratio stays within rounding noise of the run's mean."""
    segments: list[Segment] = []
    run: list[float] = []
    start = prev = None
    for day, ratio in ratios.items():
        tol = RATIO_NOISE_FLOOR + ROUNDING / float(raw_closes[day])
        if run and abs(ratio - sum(run) / len(run)) > tol:
            segments.append(Segment(start, prev, len(run), sum(run) / len(run)))
            run = []
        if not run:
            start = day
        run.append(float(ratio))
        prev = day
    if run:
        segments.append(Segment(start, prev, len(run), sum(run) / len(run)))
    return segments


def stray_steps(segments: list[Segment], actions: pd.DataFrame) -> int:
    """Segment boundaries with no dividend/split ex-date since the previous segment ended."""
    events = pd.to_datetime(actions["Date"]).sort_values()
    stray = 0
    for before, after in zip(segments, segments[1:]):
        if not ((events > before.end) & (events <= after.start)).any():
            stray += 1
    return stray


def _off_basis_unmatched(stored: pd.DataFrame, raw: pd.DataFrame, ratios: pd.Series) -> pd.Index:
    """Stored dates Yahoo lacks whose nearest shared-date ratio is off the raw basis."""
    s = _by_day(stored)
    missing = s.index.difference(_by_day(raw).index)
    if missing.empty or ratios.empty:
        return missing
    nearest = ratios.reindex(ratios.index.union(missing)).sort_index()
    nearest = nearest.ffill().bfill()[missing]
    return missing[((nearest - 1.0).abs() > KEEP_TOLERANCE).to_numpy()]


def compare(path: Path, stored: pd.DataFrame, raw: pd.DataFrame, actions: pd.DataFrame) -> Rebase:
    report = Rebase(path=path, rows=len(stored), actions=actions)
    ratios, raw_closes = ratio_series(stored, raw)
    report.shared = len(ratios)
    if not ratios.empty:
        report.max_dev = float((ratios - 1.0).abs().max())
        report.segments = basis_segments(ratios, raw_closes)
        report.stray = stray_steps(report.segments, actions)
    s_close = pd.to_numeric(_by_day(stored)["Close"], errors="coerce")
    r_close = pd.to_numeric(_by_day(raw)["Close"], errors="coerce")
    shared = s_close.index.intersection(r_close.index)
    diff = (s_close[shared] - r_close[shared]).abs()
    report.changed = int((diff > CLOSE_CHANGE).sum())
    report.refined = int(((diff <= CLOSE_CHANGE) & (diff > SAME_CLOSE_RTOL * r_close[shared].abs())).sum())
    report.added = len(r_close.index.difference(s_close.index))
    drop = _off_basis_unmatched(stored, raw, ratios)
    report.dropped = len(drop)
    report.dividends = int((actions["Action"] == DIVIDEND).sum())
    report.splits = int((actions["Action"] == SPLIT).sum())
    report.frame = _rebased_frame(stored, raw, drop)
    return report


def _rebased_frame(stored: pd.DataFrame, raw: pd.DataFrame, drop: pd.Index) -> pd.DataFrame:
    columns = list(stored.columns)
    raw_rows = _by_day(raw)
    keep = _by_day(stored)
    keep = keep.loc[~keep.index.isin(raw_rows.index) & ~keep.index.isin(drop)]
    frame = pd.concat([raw_rows, keep]).sort_index().reset_index()
    frame["Date"] = frame["Date"].astype("datetime64[ms]")
    return frame.reindex(columns=columns)


def ticker_from_path(path: Path) -> tuple[str, str]:
    symbol, _, exchange = path.stem.rpartition("_")
    return symbol, exchange


def fetch_raw(symbol: str, exchange: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Yahoo traded prices and actions for the stored range (no request-path side effects)."""
    from backend.timeseries.fetch_yahoo_timeseries import _build_full_ticker, fetch_yahoo_history

    return fetch_yahoo_history(_build_full_ticker(symbol, exchange), start.date(), end.date())


def rebase_file(path: Path, fetcher: Fetcher | None = None) -> Rebase:
    stored = pd.read_parquet(path)
    if stored.empty:
        return Rebase(path=path, rows=0, error="empty")
    dates = pd.to_datetime(stored["Date"])
    symbol, exchange = ticker_from_path(path)
    try:
        raw, actions = (fetcher or fetch_raw)(symbol, exchange, dates.min(), dates.max())
    except Exception as exc:
        logger.warning("%s: Yahoo re-fetch failed: %s", path.name, exc)
        return Rebase(path=path, rows=len(stored), error=str(exc)[:60])
    return compare(path, stored, raw, actions)


def format_header() -> str:
    return (
        f"{'file':<16} {'rows':>6} {'shared':>6} {'max|s/r-1|':>10} {'segments':>8} {'stray':>5} "
        f"{'change':>6} {'refine':>6} {'add':>5} {'drop':>5} {'divs':>5} {'splits':>6}"
    )


def format_report(r: Rebase) -> str:
    if r.error:
        return f"{r.path.name:<16} {r.rows:>6}  ERROR {r.error}"
    return (
        f"{r.path.name:<16} {r.rows:>6} {r.shared:>6} {r.max_dev:>10.4f} {len(r.segments):>8} {r.stray:>5} "
        f"{r.changed:>6} {r.refined:>6} {r.added:>5} {r.dropped:>5} {r.dividends:>5} {r.splits:>6}"
    )


def format_segments(r: Rebase) -> list[str]:
    return [f"    {s.start.date()} .. {s.end.date()}  rows={s.rows:<5} stored/raw={s.ratio:.4f}" for s in r.segments]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, help="timeseries/meta directory to scan")
    parser.add_argument("--ticker", action="append", help="limit to these file stems, e.g. VHYL_L")
    parser.add_argument("--segments", action="store_true", help="list each basis segment")
    parser.add_argument("--apply", action="store_true", help="rewrite files and store actions (default: dry run)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    paths = sorted(args.directory.glob("*.parquet"))
    if args.ticker:
        wanted = {t.upper() for t in args.ticker}
        paths = [p for p in paths if p.stem.upper() in wanted]
    print(format_header())
    for path in paths:
        report = rebase_file(path)
        print(format_report(report))
        if args.segments:
            for line in format_segments(report):
                print(line)
        if args.apply and not report.error:
            if report.changed or report.refined or report.added or report.dropped:
                report.frame.to_parquet(path, index=False)
            symbol, exchange = ticker_from_path(path)
            record_corporate_actions(symbol, exchange, report.actions, base=str(args.directory.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
