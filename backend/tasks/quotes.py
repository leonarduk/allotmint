from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Dict, Any

import boto3
import requests

from backend.config import config

log = logging.getLogger("tasks.quotes")

BASE_URL = "https://www.alphavantage.co/query"
TABLE_NAME = os.environ.get("QUOTES_TABLE", "Quotes")


def fetch_quote(symbol: str, api_key: str | None = None) -> Dict[str, Any]:
    """Fetch a single quote from Alpha Vantage."""
    if not config.alpha_vantage_enabled:
        raise RuntimeError("Alpha Vantage fetching disabled via config")
    key = api_key or config.alpha_vantage_key or "demo"
    params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key}
    resp = requests.get(BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("Global Quote", {})
    price = data.get("05. price")
    volume = data.get("06. volume")
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "symbol": symbol.upper(),
        "price": Decimal(str(price)) if price is not None else None,
        "volume": int(volume) if volume is not None else None,
        "time": timestamp,
    }


def save_quotes(items: Iterable[Dict[str, Any]], table_name: str = TABLE_NAME) -> None:
    """Save quotes to DynamoDB."""
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    for item in items:
        clean = {k: v for k, v in item.items() if v is not None}
        table.put_item(Item=clean)


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """AWS Lambda entry point."""
    symbols = event.get("symbols") if isinstance(event, dict) else None
    if not symbols:
        symbols_env = os.environ.get("SYMBOLS", "")
        symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
    items = [fetch_quote(sym) for sym in symbols]
    save_quotes(items)
    return {"count": len(items)}


if __name__ == "__main__":
    syms = os.environ.get("SYMBOLS", "IBM").split(",")
    quotes = [fetch_quote(s) for s in syms]
    save_quotes(quotes)
