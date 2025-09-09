"""Simple news retrieval endpoint."""

from __future__ import annotations

from typing import List, Dict

import logging
import requests
from fastapi import APIRouter, BackgroundTasks, Query

from backend.config import config
from backend.utils import page_cache

router = APIRouter(tags=["news"])

NEWS_TTL = 900  # seconds
BASE_URL = "https://www.alphavantage.co/query"


def _fetch_news(ticker: str) -> List[Dict[str, str]]:
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "sort": "LATEST",
        "apikey": config.alpha_vantage_key or "demo",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        feed = data.get("feed")
        if feed is None:
            message = (
                data.get("Note")
                or data.get("Error Message")
                or data.get("Information")
                or data.get("Message")
                or "Unexpected response"
            )
            raise RuntimeError(message)
        return [{"headline": item.get("title"), "url": item.get("url")} for item in feed]
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).error("Failed to fetch news for %s: %s", ticker, exc)
        return []


@router.get("/news")
async def get_news(
    background_tasks: BackgroundTasks,
    ticker: str = Query(..., min_length=1),
) -> List[Dict[str, str]]:
    """Return recent news headlines for ``ticker``."""

    tkr = ticker.strip().upper()
    if not tkr:
        return []
    page = f"news_{tkr}"

    def _call() -> List[Dict[str, str]]:
        return _fetch_news(tkr)

    page_cache.schedule_refresh(page, NEWS_TTL, _call)
    if not page_cache.is_stale(page, NEWS_TTL):
        cached = page_cache.load_cache(page)
        if cached is not None:
            return cached

    payload = _call()
    background_tasks.add_task(page_cache.save_cache, page, payload)
    return payload
