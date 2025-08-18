from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, List

from backend.integrations.broker_api import AlpacaBroker
from backend.common.alerts import publish_alert
from backend.agent.trading_agent import _log_trade

log = logging.getLogger("tasks.trades")


def _persist_trades(trades: List[Dict[str, Any]]) -> int:
    """Persist trades using the existing trade log loader."""
    count = 0
    for t in trades:
        try:
            ts = (
                datetime.fromisoformat(t.get("timestamp"))
                if t.get("timestamp")
                else None
            )
            _log_trade(t.get("ticker", ""), t.get("action", ""), float(t.get("price", 0)), ts)
            count += 1
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("failed to persist trade %s: %s", t, exc)
    return count


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Fetch recent trades from the broker and persist them."""
    since = event.get("since")
    since_dt = datetime.fromisoformat(since) if since else None
    broker = AlpacaBroker()
    try:
        trades = broker.fetch_trades(since_dt)
        saved = _persist_trades(trades)
        publish_alert({
            "ticker": "TRADES",
            "change_pct": 0,
            "message": f"Imported {saved} trades",
        })
        return {"count": saved}
    except Exception as exc:  # pragma: no cover - network errors
        log.exception("trade import failed")
        publish_alert({
            "ticker": "TRADES",
            "change_pct": 0,
            "message": f"Trade import failed: {exc}",
        })
        return {"error": str(exc)}
