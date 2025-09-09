"""Simple news retrieval endpoint."""

from __future__ import annotations

from typing import List, Dict

import logging
import json
from datetime import date
from pathlib import Path

import requests
from fastapi import APIRouter, BackgroundTasks, Query

from backend.config import config
from backend.utils import page_cache

router = APIRouter(tags=["news"])

NEWS_TTL = 900  # seconds
BASE_URL = "https://www.alphavantage.co/query"
COUNTER_FILE: Path = page_cache.CACHE_DIR / "news_requests.json"


def _load_counter() -> Dict[str, int]:
    today = date.today().isoformat()
    if COUNTER_FILE.exists():
        try:
            with COUNTER_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                if data.get("date") == today:
                    return {"date": today, "count": int(data.get("count", 0))}
        except (OSError, json.JSONDecodeError):
            pass
    return {"date": today, "count": 0}


def _save_counter(data: Dict[str, int]) -> None:
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with COUNTER_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _can_request_news() -> bool:
    data = _load_counter()
    return data["count"] < config.news_requests_per_day


def _try_consume_quota() -> bool:
    data = _load_counter()
    if data["count"] >= config.news_requests_per_day:
        return False
    data["count"] += 1
    _save_counter(data)
    return True


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
        return [
            {"headline": item.get("title"), "url": item.get("url")} for item in feed
        ]
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
        if not _try_consume_quota():
            raise RuntimeError("news quota exceeded")
        return _fetch_news(tkr)

    page_cache.schedule_refresh(page, NEWS_TTL, _call, can_refresh=_can_request_news)
    if not page_cache.is_stale(page, NEWS_TTL):
        cached = page_cache.load_cache(page)
        if cached is not None:
            return cached

    try:
        payload = _call()
    except RuntimeError:
        cached = page_cache.load_cache(page)
        if cached is not None:
            return cached
        raise HTTPException(status_code=429, detail="News request quota exceeded")
    background_tasks.add_task(page_cache.save_cache, page, payload)
    return payload
