"""Quote endpoint backed by DynamoDB."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import List, Dict, Any

import boto3
import yfinance as yf
import sys
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api")
TABLE_NAME = os.environ.get("QUOTES_TABLE", "Quotes")
_dynamodb = None
_table = None
sys.modules[__name__ + ".yf"] = yf


def _get_table():
    global _dynamodb, _table
    if _table is None:
        _dynamodb = boto3.resource("dynamodb")
        _table = _dynamodb.Table(TABLE_NAME)
    return _table


def _convert_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}


@router.get("/quotes")
async def get_quotes(symbols: str = Query("")) -> List[Dict[str, Any]]:
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []
    try:
        yf.Tickers(" ".join(syms))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch quotes: {exc}")
    table = _get_table()
    results: List[Dict[str, Any]] = []
    for sym in syms:
        try:
            resp = table.get_item(Key={"symbol": sym})
        except Exception:
            continue
        item = resp.get("Item")
        if item:
            results.append(_convert_item(item))
    return results
