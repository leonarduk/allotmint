from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests

log = logging.getLogger("integrations.broker_api")


class BrokerAPI:
    """Abstract base class for brokerage integrations."""

    def fetch_trades(self, since: Optional[datetime] = None) -> List[Dict]:
        """Return a list of executed trades since *since* (UTC)."""
        raise NotImplementedError


class AlpacaBroker(BrokerAPI):
    """Minimal Alpaca API wrapper for fetching recent trades."""

    BASE_URL = "https://paper-api.alpaca.markets"

    def __init__(self, key: Optional[str] = None, secret: Optional[str] = None):
        self.key = key or os.getenv("ALPACA_API_KEY_ID")
        self.secret = secret or os.getenv("ALPACA_API_SECRET_KEY")

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key or "",
            "APCA-API-SECRET-KEY": self.secret or "",
        }

    def fetch_trades(self, since: Optional[datetime] = None) -> List[Dict]:
        params: Dict[str, str] = {"activity_types": "FILL"}
        if since:
            params["after"] = since.isoformat()
        url = f"{self.BASE_URL}/v2/account/activities"
        resp = requests.get(url, params=params, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        trades: List[Dict] = []
        for row in resp.json():
            trades.append(
                {
                    "ticker": row.get("symbol"),
                    "action": row.get("side", "").upper(),
                    "price": float(row.get("price", 0)),
                    "timestamp": row.get("transaction_time"),
                }
            )
        return trades
