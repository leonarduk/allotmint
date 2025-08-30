from __future__ import annotations

"""Simple brokerage API adapters.

This module exposes a very small wrapper around third party brokerage
APIs so that other parts of the system have a consistent interface.  The
adapters are intentionally lightweight and only implement the behaviour
required by the scheduled trade import task.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Protocol
import logging

import requests

log = logging.getLogger("integrations.broker")


class BrokerAPI(Protocol):
    """Minimal interface all broker adapters must implement."""

    def recent_trades(self, since: datetime) -> List[Dict[str, str]]:
        """Return trades executed after ``since``."""
        raise NotImplementedError


@dataclass
class AlpacaAPI:
    """Adapter for the public Alpaca trading API.

    Only a subset of the API surface is implemented – enough to fetch
    recent trade executions.  Authentication is provided via the standard
    ``APCA-API-KEY-ID`` and ``APCA-API-SECRET-KEY`` headers which can be
    supplied either at initialisation time or through environment
    variables.
    """

    api_key: str
    api_secret: str
    base_url: str = "https://paper-api.alpaca.markets"

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }

    def recent_trades(self, since: datetime) -> List[Dict[str, str]]:
        """Fetch recent trades from Alpaca.

        The implementation hits the ``/v2/account/activities/trades``
        endpoint which returns a list of trade activity records.  Network
        failures or unexpected responses are logged and result in an empty
        list being returned.
        """

        url = f"{self.base_url}/v2/account/activities/trades"
        params = {"after": since.isoformat()}

        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # pragma: no cover - network failure
            log.warning("Alpaca trade fetch failed: %s", exc)
            return []

        trades: List[Dict[str, str]] = []
        for item in data:
            trades.append(
                {
                    "date": item.get("transaction_time", "")[:10],
                    "ticker": item.get("symbol", ""),
                    "units": str(item.get("qty", "")),
                    "price": str(item.get("price", "")),
                }
            )
        return trades
