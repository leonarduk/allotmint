"""Find and repair cached meta timeseries that interleave price sources (#8597).

Before #8597 the meta fetcher and rolling cache could fill one provider's
gaps with another provider's rows, even when the two used different
adjustment bases (Stooq back-adjusts for dividends; Yahoo is now fetched as
the traded price, see #9340). ADM.L ended up with Stooq rows ~25% below the
Yahoo rows on neighbouring days. Same-source re-basing from the old
dividend-adjusted Yahoo fetches is handled by
``scripts/repair_dividend_basis_timeseries.py``.

For every ``<SYMBOL>_<EXCHANGE>.parquet`` with more than one ``Source``:

* Yahoo (the fetcher's first-choice provider, and the one ``--refill``
  re-fetches from) is the primary when present, else the source with the
  most rows;
* each other source is kept only if its closes match the nearest primary
  close (within ``NEIGHBOUR_DAYS``) to ``BASIS_TOLERANCE`` on median;
  otherwise all its rows are dropped;
* with ``--refill``, the dropped dates are re-fetched from Yahoo and filled
  only if that fetch is on the same basis as the rows kept.

Dry-run by default; pass ``--apply`` to rewrite the files.

    python -m scripts.repair_mixed_source_timeseries ../allotmint-data/timeseries/meta
    python -m scripts.repair_mixed_source_timeseries DIR --ticker ADM_L --refill --apply
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pandas as pd

from backend.timeseries.source_basis import BASIS_TOLERANCE, same_basis

logger = logging.getLogger(__name__)

# How far apart a minority-source row and its nearest primary row may be
# when estimating whether they share a basis.
NEIGHBOUR_DAYS = 5
# Fewer neighbouring pairs than this is too little evidence to keep a source.
MIN_NEIGHBOUR_PAIRS = 3
PREFERRED_PRIMARY = "Yahoo"
# Day-to-day move reported as a likely basis jump in the summary.
JUMP_THRESHOLD = 0.15


@dataclass
class Repair:
    path: Path
    rows_before: int
    jumps_before: int
    primary: str
    dropped: dict[str, int] = field(default_factory=dict)
    kept_sources: list[str] = field(default_factory=list)
    refilled: int = 0
    rows_after: int = 0
    jumps_after: int = 0
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)


def count_jumps(df: pd.DataFrame) -> int:
    closes = pd.to_numeric(df.sort_values("Date")["Close"], errors="coerce")
    return int((closes.pct_change().abs() > JUMP_THRESHOLD).sum())


def neighbour_ratio(primary: pd.DataFrame, other: pd.DataFrame) -> float | None:
    """Median ``other / nearest primary`` Close, or ``None`` when no neighbour is close enough."""
    left = other[["Date", "Close"]].sort_values("Date")
    right = primary[["Date", "Close"]].sort_values("Date").rename(columns={"Close": "PrimaryClose"})
    paired = pd.merge_asof(
        left, right, on="Date", direction="nearest", tolerance=pd.Timedelta(days=NEIGHBOUR_DAYS)
    ).dropna(subset=["PrimaryClose"])
    paired = paired[(paired["Close"] > 0) & (paired["PrimaryClose"] > 0)]
    if len(paired) < MIN_NEIGHBOUR_PAIRS:
        return None
    return float((paired["Close"] / paired["PrimaryClose"]).median())


def split_sources(df: pd.DataFrame, report: Repair) -> pd.DataFrame:
    """Return the primary rows plus any other source on the same basis; record what was dropped."""
    sources = df["Source"].astype("string").fillna("")
    primary = df.loc[sources == report.primary]
    keep = [primary]
    for source in sources.value_counts().index:
        if source == report.primary:
            continue
        rows = df.loc[sources == source]
        ratio = neighbour_ratio(primary, rows)
        if ratio is not None and abs(ratio - 1.0) <= BASIS_TOLERANCE:
            keep.append(rows)
            report.kept_sources.append(source)
        else:
            report.dropped[source] = len(rows)
            logger.info("%s: dropping %d %s rows (ratio %s)", report.path.name, len(rows), source, ratio)
    return pd.concat(keep, ignore_index=True)


def ticker_from_path(path: Path) -> tuple[str, str]:
    symbol, _, exchange = path.stem.rpartition("_")
    return symbol, exchange


def refill_from_yahoo(kept: pd.DataFrame, dropped: pd.DataFrame, path: Path, primary: str) -> pd.DataFrame:
    """Return Yahoo rows for dates in ``dropped`` that ``kept`` lacks, if Yahoo matches the primary's basis."""
    from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range

    symbol, exchange = ticker_from_path(path)
    start = dropped["Date"].min().date() - timedelta(days=NEIGHBOUR_DAYS * 2)
    end = dropped["Date"].max().date() + timedelta(days=NEIGHBOUR_DAYS * 2)
    fetched = fetch_yahoo_timeseries_range(symbol, exchange, start, end)
    fetched["Date"] = pd.to_datetime(fetched["Date"]).astype("datetime64[ms]")
    if not same_basis(kept.loc[kept["Source"] == primary], fetched):
        logger.warning("%s: Yahoo refill is not on the cached basis; leaving gaps", path.name)
        return fetched.iloc[0:0]
    wanted = set(_day(dropped)) - set(_day(kept))
    return fetched.loc[_day(fetched).isin(wanted).to_numpy()]


def _day(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["Date"]).dt.normalize().astype("datetime64[ns]")


def repair_file(path: Path, *, refill: bool) -> Repair | None:
    df = pd.read_parquet(path)
    sources = df["Source"].astype("string").fillna("")
    if sources.nunique() < 2:
        return None
    counts = sources.value_counts()
    primary = PREFERRED_PRIMARY if PREFERRED_PRIMARY in counts.index else counts.index[0]
    report = Repair(path=path, rows_before=len(df), jumps_before=count_jumps(df), primary=primary)
    kept = split_sources(df, report)
    if refill and report.dropped:
        dropped = df.loc[sources.isin(list(report.dropped)).to_numpy()]
        extra = refill_from_yahoo(kept, dropped, path, report.primary)
        report.refilled = len(extra)
        kept = pd.concat([kept, extra[df.columns]], ignore_index=True)
    repaired = kept.sort_values("Date").reset_index(drop=True)[df.columns]
    report.rows_after = len(repaired)
    report.jumps_after = count_jumps(repaired)
    report.frame = repaired
    return report


def format_report(r: Repair) -> str:
    dropped = ", ".join(f"{s}:{n}" for s, n in r.dropped.items()) or "-"
    kept = ", ".join(r.kept_sources) or "-"
    return (
        f"{r.path.name:<20} primary={r.primary:<12} dropped={dropped:<16} kept-other={kept:<10} "
        f"refilled={r.refilled:<5} rows {r.rows_before}->{r.rows_after}  "
        f">{JUMP_THRESHOLD:.0%} moves {r.jumps_before}->{r.jumps_after}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, help="timeseries/meta directory to scan")
    parser.add_argument("--ticker", action="append", help="limit to these file stems, e.g. ADM_L")
    parser.add_argument("--refill", action="store_true", help="re-fetch dropped dates from Yahoo")
    parser.add_argument("--apply", action="store_true", help="rewrite repaired files (default: dry run)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    paths = sorted(args.directory.glob("*.parquet"))
    if args.ticker:
        paths = [p for p in paths if p.stem in set(args.ticker)]
    for path in paths:
        report = repair_file(path, refill=args.refill)
        if report is None:
            continue
        print(format_report(report))
        if args.apply and (report.dropped or report.refilled):
            report.frame.to_parquet(path, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
