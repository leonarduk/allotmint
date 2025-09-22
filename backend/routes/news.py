"""Simple news retrieval endpoint."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
import xml.etree.ElementTree as ET
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from email.utils import parsedate_to_datetime

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


def _isoformat(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    # Normalise to UTC with seconds precision
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    value = dt.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def _clean_str(value: object) -> Optional[str]:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def fetch_news_yahoo(ticker: str) -> List[Dict[str, Optional[str]]]:
    """Fetch headlines from Yahoo Finance search API."""

    endpoint = cfg.yahoo_news_endpoint or "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": ticker, "quotesCount": 0, "newsCount": 10}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("news", [])
    out: List[Dict[str, Optional[str]]] = []
    for item in items:
        title = _clean_str(item.get("title"))
        link = _clean_str(item.get("link"))
        if title and link:
            source = _clean_str(
                item.get("publisher") or item.get("source") or item.get("provider")
            )
            published_at: Optional[str] = None
            publish_ts = item.get("providerPublishTime")
            if isinstance(publish_ts, (int, float)):
                published_at = _isoformat(datetime.fromtimestamp(publish_ts, tz=timezone.utc))
            elif isinstance(publish_ts, str):
                try:
                    published_at = _isoformat(
                        datetime.fromtimestamp(float(publish_ts), tz=timezone.utc)
                    )
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    published_at = None
            out.append(
                {
                    "headline": title,
                    "url": link,
                    "source": source,
                    "published_at": published_at,
                }
            )
    return out


def fetch_news_google(ticker: str) -> List[Dict[str, Optional[str]]]:
    """Fetch headlines from Google Finance via RSS search."""

    endpoint = cfg.google_news_endpoint or "https://news.google.com/rss/search"
    params = {"q": ticker, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: List[Dict[str, Optional[str]]] = []
    for item in root.findall(".//item"):
        title = _clean_str(item.findtext("title"))
        link = _clean_str(item.findtext("link"))
        if title and link:
            published_at = item.findtext("pubDate")
            parsed_dt: Optional[datetime] = None
            if published_at:
                try:
                    parsed_dt = parsedate_to_datetime(published_at)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    parsed_dt = None
            source_text = _clean_str(item.findtext("{http://news.google.com}source"))
            out.append(
                {
                    "headline": title,
                    "url": link,
                    "source": source_text,
                    "published_at": _isoformat(parsed_dt),
                }
            )
    return out


def _parse_alpha_time(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None

    try:
        cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        except ValueError:
            return None
        dt = dt.replace(tzinfo=timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return _isoformat(dt)


def _fetch_news(ticker: str) -> List[Dict[str, Optional[str]]]:
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
            enriched: List[Dict[str, Optional[str]]] = []
            for item in feed:
                title = _clean_str(item.get("title"))
                url = _clean_str(item.get("url"))
                if not (title and url):
                    continue
                enriched.append(
                    {
                        "headline": title,
                        "url": url,
                        "source": _clean_str(item.get("source")),
                        "published_at": _parse_alpha_time(item.get("time_published")),
                    }
                )
            if enriched:
                return enriched
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


def get_cached_news(
    ticker: str,
    *,
    cache_writer: Callable[[str, List[Dict[str, Optional[str]]]], None] | None = None,
    raise_on_quota_exhausted: bool = False,
) -> List[Dict[str, Optional[str]]]:
    """Return cached or freshly fetched news for ``ticker``.

    The helper mirrors the caching and quota handling used by the ``/news``
    endpoint so that other modules can reuse the same logic synchronously.
    When ``cache_writer`` is provided it is invoked to persist fresh payloads;
    otherwise the helper writes to ``page_cache`` directly.  If the quota is
    exhausted and no cached payload is available a ``RuntimeError`` is raised
    when ``raise_on_quota_exhausted`` is true.
    """

    tkr = ticker.strip().upper()
    if not tkr:
        return []

    page = f"news_{tkr}"

    def _call() -> List[Dict[str, Optional[str]]]:
        if not _try_consume_quota():
            raise RuntimeError("news quota exceeded")
        return _fetch_news(tkr)

    page_cache.schedule_refresh(page, NEWS_TTL, _call, can_refresh=_can_request_news)

    cached = page_cache.load_cache(page)
    if cached is not None and not page_cache.is_stale(page, NEWS_TTL):
        return cached

    try:
        payload = _call()
    except RuntimeError:
        if cached is not None:
            return cached
        if raise_on_quota_exhausted:
            raise
        return []

    if cache_writer is not None:
        cache_writer(page, payload)
    else:
        page_cache.save_cache(page, payload)
    return payload


@router.get("/news")
async def get_news(
    background_tasks: BackgroundTasks,
    ticker: str = Query(..., min_length=1),
) -> List[Dict[str, str]]:
    """Return recent news headlines for ``ticker``."""

    tkr = ticker.strip().upper()
    if not tkr:
        return []
    try:
        return get_cached_news(
            tkr,
            cache_writer=lambda page, data: background_tasks.add_task(
                page_cache.save_cache, page, data
            ),
            raise_on_quota_exhausted=True,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail="News request quota exceeded") from exc
