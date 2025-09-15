"""Simple news retrieval endpoint."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List

import requests
import xml.etree.ElementTree as ET
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend import config_module
from backend.utils import page_cache

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

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
    return data["count"] < cfg.news_requests_per_day


def _try_consume_quota() -> bool:
    data = _load_counter()
    if data["count"] >= cfg.news_requests_per_day:
        return False
    data["count"] += 1
    _save_counter(data)
    return True


def fetch_news_yahoo(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Yahoo Finance search API."""

    endpoint = cfg.yahoo_news_endpoint or "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": ticker, "quotesCount": 0, "newsCount": 10}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("news", [])
    out: List[Dict[str, str]] = []
    for item in items:
        title = item.get("title")
        link = item.get("link")
        if title and link:
            out.append({"headline": title, "url": link})
    return out


def fetch_news_google(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Google Finance via RSS search."""

    endpoint = cfg.google_news_endpoint or "https://news.google.com/rss/search"
    params = {"q": ticker, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        if title and link:
            out.append({"headline": title, "url": link})
    return out


def _fetch_news(ticker: str) -> List[Dict[str, str]]:
    """Fetch news from AlphaVantage with fallbacks to Yahoo and Google."""

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "sort": "LATEST",
        "apikey": cfg.alpha_vantage_key or "demo",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        feed = data.get("feed") or []
        if feed:
            return [
                {"headline": item.get("title"), "url": item.get("url")}
                for item in feed
            ]
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).error(
            "Failed to fetch news for %s: %s", ticker, exc
        )

    for fetcher in (fetch_news_yahoo, fetch_news_google):
        try:
            items = fetcher(ticker)
            if items:
                return items
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).error(
                "Fallback news fetch failed for %s: %s", ticker, exc
            )
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
