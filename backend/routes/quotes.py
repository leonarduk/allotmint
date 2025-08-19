# backend/routes/quotes.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query

import yfinance as yf

router = APIRouter(prefix="/api", tags=["quotes"])


@router.get("/quotes")
def get_quotes(symbols: str = Query("")) -> List[Dict[str, float]]:
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return []
    try:
        data = yf.Tickers(" ".join(syms))
    except Exception as e:  # pragma: no cover - error path tested via monkeypatch
        raise HTTPException(status_code=502, detail=f"Failed to fetch quotes: {e}")

    results: List[Dict[str, float]] = []
    for sym in syms:
        ticker = data.tickers.get(sym)
        if not ticker:
            continue
        price = ticker.info.get("regularMarketPrice")
        if price is not None:
            results.append({"symbol": sym, "price": float(price)})
    return results

