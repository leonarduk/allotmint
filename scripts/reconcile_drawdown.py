#!/usr/bin/env python3
"""reconcile_drawdown
=====================

Inspect portfolio drawdowns for an owner or group.

This script computes the per-day portfolio value and maximum drawdown over a
specified window. Significant daily drops trigger a dump of each holding's
price history to CSV and JSON for manual inspection.

Usage examples::

    python scripts/reconcile_drawdown.py alice --days 180
    python scripts/reconcile_drawdown.py --group family --days 90 --ticker VUSA.L --ticker MSFT

The ``--ticker`` option may be repeated to restrict which instruments are
exported. By default the script writes price data for all holdings when a
significant drop is detected.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

from backend.common import portfolio as portfolio_mod
from backend.common import group_portfolio, instrument_api, portfolio_utils
from backend.timeseries.cache import load_meta_timeseries


DROP_THRESHOLD = 0.05  # 5% daily decline


def _gather_holdings(name: str, *, group: bool) -> List[Tuple[str, str]]:
    """Return ``(ticker, exchange)`` tuples for all holdings."""

    if group:
        pf = group_portfolio.build_group_portfolio(name)
    else:
        pf = portfolio_mod.build_owner_portfolio(name)

    holdings: List[Tuple[str, str]] = []
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            resolved = instrument_api._resolve_full_ticker(
                tkr, portfolio_utils._PRICE_SNAPSHOT
            )
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
            exch = (h.get("exchange") or inferred or "L").upper()
            holdings.append((sym, exch))
    return holdings


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile portfolio drawdowns")
    parser.add_argument("owner", nargs="?", help="Owner slug to inspect")
    parser.add_argument("--group", help="Group slug to inspect")
    parser.add_argument("--days", type=int, default=365, help="Lookback window")
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        default=[],
        help="Limit output to specific ticker (repeatable)",
    )
    args = parser.parse_args()

    name = args.group or args.owner
    if not name:
        parser.error("owner or --group is required")
    is_group = bool(args.group)

    drawdown = (
        portfolio_utils.compute_group_max_drawdown(name, args.days)
        if is_group
        else portfolio_utils.compute_max_drawdown(name, args.days)
    )
    if drawdown is None:
        print("No drawdown data available")
    else:
        print(f"Max drawdown over {args.days} days: {drawdown:.2%}")

    series = portfolio_utils._portfolio_value_series(name, args.days, group=is_group)
    if series.empty:
        print("No portfolio value data")
        return
    print("\nPortfolio value by day:\n")
    print(series.to_string())

    returns = series.pct_change().dropna()
    drops = returns[returns <= -DROP_THRESHOLD]
    if drops.empty:
        print("\nNo drops exceeded threshold")
        return

    print("\nSignificant drops:")
    for d, val in drops.items():
        print(f"{d}: {val:.2%}")

    holdings = _gather_holdings(name, group=is_group)
    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        holdings = [h for h in holdings if h[0].upper() in wanted]

    for tkr, exch in holdings:
        df = load_meta_timeseries(tkr, exch, args.days)
        if df.empty:
            print(f"No data for {tkr}.{exch}")
            continue
        base = f"{tkr}.{exch}"
        csv_path = Path(f"{base}.csv")
        json_path = Path(f"{base}.json")
        df.to_csv(csv_path, index=False)
        df.to_json(json_path, orient="records", date_format="iso")
        print(f"Wrote {csv_path} and {json_path}")


if __name__ == "__main__":
    main()
