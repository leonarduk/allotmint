"""Refresh the ``look_through`` block (countries, sectors, top holdings) of fund metadata.

For every fund under ``<data_root>/instruments/<EXCHANGE>/<SYMBOL>.json`` with an
ISIN, fetches its latest breakdown from Morningstar (justETF as fallback) via
:mod:`backend.common.look_through_sources` and stores it as ``look_through``,
keeping each file's key order so the diff shows only that block. Dry-run by
default; ``--write`` saves. Requests are throttled and recently fetched funds
are skipped, because neither source is an official API (#9974).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

import requests

from backend.common.instrument_classification import COMMODITY, derive_asset_class, is_fund, overrides_path
from backend.common.look_through_sources import LookThroughFetchError, fetch_look_through, new_session

logger = logging.getLogger(__name__)

DEFAULT_DELAY_S = 1.5
DEFAULT_MAX_AGE_DAYS = 25


def _ticker_for(path: Path, meta: dict[str, Any]) -> str:
    raw = meta.get("ticker")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return f"{path.stem.upper()}.{path.parent.name.upper()}"


def _is_fresh(meta: dict[str, Any], today: date, max_age_days: int) -> bool:
    block = meta.get("look_through")
    fetched = block.get("fetched") if isinstance(block, dict) else None
    try:
        return bool(fetched) and date.fromisoformat(str(fetched)) >= today - timedelta(days=max_age_days)
    except ValueError:
        return False


def candidate_funds(instruments_dir: Path, tickers: Optional[set[str]] = None) -> Iterator[tuple[Path, dict[str, Any]]]:
    """``(path, metadata)`` for each non-commodity fund with an ISIN (optionally only ``tickers``)."""
    for path in sorted(instruments_dir.glob("*/*.json")):
        if path.parent.name in ("groupings", "Cash"):
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Skipping unreadable %s: %s", path, exc)
            continue
        if not isinstance(meta, dict) or not meta.get("isin"):
            continue
        ticker = _ticker_for(path, meta)
        if tickers is not None and ticker not in tickers:
            continue
        if tickers is None and (not is_fund(meta) or derive_asset_class(meta) == COMMODITY):
            continue
        yield path, meta


def refresh_file(
    path: Path, meta: dict[str, Any], session: requests.Session, *, today: date, write: bool
) -> Optional[dict[str, Any]]:
    """Fetch and (with ``write``) store one fund's block; return it, or ``None`` if no source covers the fund."""
    block = fetch_look_through(str(meta["isin"]), session, today)
    if block is not None and write:
        meta["look_through"] = block
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return block


def _summary(block: dict[str, Any]) -> str:
    countries = ", ".join(f"{k} {v:.1f}%" for k, v in list(block["countries"].items())[:3])
    return f"{block['source']} as of {block.get('as_of')}: {countries}; {len(block['top_holdings'])} top holdings"


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] + " (dry-run by default).")
    parser.add_argument("--instruments-dir", type=Path, default=None, help="Default: <data_root>/instruments")
    parser.add_argument("--ticker", action="append", default=None, help="Only this ticker (e.g. VWRL.L); repeatable")
    parser.add_argument("--write", action="store_true", help="Save changes (default: report only)")
    parser.add_argument("--force", action="store_true", help="Refetch even if fetched recently")
    parser.add_argument(
        "--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS, help="Skip blocks fetched within N days"
    )
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_S, help="Seconds between funds (throttle)")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    instruments_dir = args.instruments_dir or overrides_path().parent / "instruments"
    if not instruments_dir.is_dir():
        raise SystemExit(f"instruments directory not found: {instruments_dir}")
    tickers = {t.strip().upper() for t in args.ticker} if args.ticker else None
    today = date.today()
    session = new_session()
    counts = {"updated": 0, "fresh": 0, "uncovered": 0, "failed": 0}
    for path, meta in candidate_funds(instruments_dir, tickers):
        label = path.relative_to(instruments_dir).as_posix()
        if not args.force and _is_fresh(meta, today, args.max_age_days):
            counts["fresh"] += 1
            continue
        try:
            block = refresh_file(path, meta, session, today=today, write=args.write)
        except (requests.RequestException, LookThroughFetchError) as exc:
            logger.error("%s: fetch failed: %s", label, exc)
            counts["failed"] += 1
        else:
            counts["updated" if block else "uncovered"] += 1
            print(f"{label}: {_summary(block) if block else 'no look-through data'}")
        time.sleep(max(args.delay, 0.0))
    verb = "Updated" if args.write else "Would update"
    print(
        f"{verb} {counts['updated']}; {counts['fresh']} fresh (skipped); "
        f"{counts['uncovered']} not covered; {counts['failed']} failed"
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
