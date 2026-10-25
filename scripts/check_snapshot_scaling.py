"""Check that a deployed price snapshot applies the scaling overrides (#10352).

``prices/latest_prices.json`` stores scaled GBP: ``get_scaling_override`` is
applied before ``last_price`` is written (#8923). A regression that drops an
override (or replaces the table with a stale copy) ships prices 100x wrong
without failing anything, so this compares, for every ticker-specific entry
in ``scaling_overrides.json``, the snapshot ``last_price`` with the raw last
close in the meta timeseries cache. Overrides are applied at read time only,
so the cached close is the unscaled feed value (#8597).

Absolute prices move with the market, so the check is on the ratio
``last_price / raw_close``, which must be within a factor of three of the
override factor (a 100x slip is far outside that; a market move or a live
quote a few days newer than the cached close is not). Tickers absent from
the snapshot (holdings drive the refresh universe) or without a cached
series are skipped with a ``::notice::``.

    python -m scripts.check_snapshot_scaling latest_prices.json data/timeseries
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from backend.utils.timeseries_helpers import get_scaling_override, scaling_override_paths

# How far the observed ratio may drift from the override factor before it is
# treated as the wrong scale. Pence/pounds mistakes are exactly 100x.
RATIO_TOLERANCE = 3.0


@dataclass(frozen=True)
class Result:
    ticker: str
    ok: bool
    skipped: bool
    message: str


def override_tickers() -> list[tuple[str, str]]:
    """``(symbol, exchange)`` for every ticker-specific override, sorted.

    Read from the same tables ``get_scaling_override`` merges; wildcard
    rows apply to many tickers and have no single series to compare with.
    """
    pairs: set[tuple[str, str]] = set()
    for path in scaling_override_paths():
        table = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(table, dict):
            raise ValueError(f"{path}: expected a JSON object")
        for exchange, section in table.items():
            if exchange == "*" or not isinstance(section, dict):
                continue
            pairs.update((str(sym).upper(), str(exchange).upper()) for sym in section if sym != "*")
    return sorted(pairs)


def meta_cache_file(cache_dir: Path, symbol: str, exchange: str) -> Path:
    """Local path of a meta series; mirrors ``backend.timeseries.cache.meta_timeseries_cache_path``.

    That helper resolves against the process-wide cache base fixed at import,
    so it cannot point at the directory given on the command line.
    """
    return cache_dir / "meta" / f"{symbol.upper()}_{exchange.upper()}.parquet"


def raw_last_close(path: Path) -> float | None:
    """The latest finite close in the cached series at ``path``, or None."""
    frame = pd.read_parquet(path, columns=["Date", "Close"])
    closes = pd.to_numeric(frame.sort_values("Date")["Close"], errors="coerce").dropna()
    return float(closes.iloc[-1]) if not closes.empty else None


def _snapshot_price(snapshot: dict, ticker: str) -> float | None:
    for key, info in snapshot.items():
        if str(key).upper() == ticker and isinstance(info, dict):
            price = info.get("last_price")
            if isinstance(price, (int, float)) and math.isfinite(price) and price > 0:
                return float(price)
    return None


def check_ticker(snapshot: dict, cache_dir: Path, symbol: str, exchange: str) -> Result:
    ticker = f"{symbol}.{exchange}"
    price = _snapshot_price(snapshot, ticker)
    if price is None:
        return Result(ticker, True, True, f"{ticker} has no price in the snapshot; skipped")
    cache_file = meta_cache_file(cache_dir, symbol, exchange)
    if not cache_file.is_file():
        return Result(ticker, True, True, f"{ticker} has no cached series at {cache_file}; skipped")
    raw = raw_last_close(cache_file)
    if raw is None or raw <= 0:
        return Result(ticker, True, True, f"{ticker} has no usable close in {cache_file}; skipped")

    factor = get_scaling_override(symbol, exchange, None)
    ratio = price / raw
    detail = f"{ticker}: last_price={price:g}, raw close={raw:g}, ratio={ratio:g}, factor={factor:g}"
    if factor / RATIO_TOLERANCE <= ratio <= factor * RATIO_TOLERANCE:
        return Result(ticker, True, False, detail)
    return Result(ticker, False, False, f"{detail} -- snapshot price is at the wrong scale")


def run(snapshot_path: Path, cache_dir: Path) -> list[Result]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError(f"{snapshot_path}: expected a JSON object")
    return [check_ticker(snapshot, cache_dir, sym, exch) for sym, exch in override_tickers()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", type=Path, help="Path to a latest_prices.json snapshot")
    parser.add_argument("cache_dir", type=Path, help="Timeseries cache directory (contains meta/)")
    args = parser.parse_args(argv)

    results = run(args.snapshot, args.cache_dir)
    for result in results:
        if result.skipped:
            print(f"::notice::{result.message}")
        elif result.ok:
            print(f"OK {result.message}")
        else:
            print(f"::error::{result.message}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
