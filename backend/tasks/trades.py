from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from backend.common.alerts import publish_alert
from backend.common.portfolio import load_trades, _local_trades_path
from backend.integrations.broker_api import AlpacaAPI

log = logging.getLogger("tasks.trades")


def persist_trades(owner: str, trades: List[Dict[str, Any]]) -> int:
    """Append ``trades`` to the owner's trade log.

    Trades are stored in ``data/accounts/<owner>/trades.csv`` using the
    same loader helpers as the rest of the application.  Existing entries
    are preserved and the combined log is written back atomically.
    """

    if not trades:
        return 0

    existing = load_trades(owner)
    path = _local_trades_path(owner)
    path.parent.mkdir(parents=True, exist_ok=True)
    all_trades = existing + trades
    fieldnames = sorted({k for t in all_trades for k in t.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_trades:
            writer.writerow(row)
    return len(trades)


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Scheduled entry point used by AWS Lambda.

    Environment variables provide credentials and owner details:

    ``ALPACA_KEY`` and ``ALPACA_SECRET`` - authentication for the broker
    ``TRADES_OWNER`` - which owner's trade log to update
    """

    key = os.environ.get("ALPACA_KEY", "")
    secret = os.environ.get("ALPACA_SECRET", "")
    owner = event.get("owner") or os.environ.get("TRADES_OWNER", "default")

    broker = AlpacaAPI(api_key=key, api_secret=secret)

    since_str = event.get("since") or os.environ.get("TRADES_SINCE")
    if since_str:
        since = datetime.fromisoformat(since_str)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=1)

    trades = broker.recent_trades(since)
    saved = persist_trades(owner, trades)

    publish_alert(
        {
            "ticker": "IMPORT",
            "change_pct": 0.0,
            "message": f"Imported {saved} trades for {owner}",
        }
    )

    return {"count": saved}


if __name__ == "__main__":
    # Manual execution for local testing
    result = lambda_handler({}, None)
    log.info("Imported %s trades", result.get("count"))
