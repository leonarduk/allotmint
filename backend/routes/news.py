"""Simple news retrieval endpoint."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
import xml.etree.ElementTree as ET
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend import config_module
from backend.common.instruments import get_instrument_meta
from backend.utils import page_cache

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

router = APIRouter(tags=["news"])

NEWS_TTL = 900  # seconds
BASE_URL = "https://www.alphavantage.co/query"
COUNTER_FILE: Path = page_cache.CACHE_DIR / "news_requests.json"

_FINANCE_KEYWORDS = (
    "stock",
    "stocks",
    "share",
    "shares",
    "earnings",
    "ipo",
    "dividend",
    "market",
    "financial",
    "finance",
    "guidance",
    "outlook",
    "profit",
    "loss",
    "revenue",
    "price",
)



def _make_news_item(headline: object, url: object) -> Dict[str, str] | None:
    """Return a minimal news item when both ``headline`` and ``url`` are valid."""

    clean_headline = _clean_str(headline)
    clean_url = _clean_str(url)
    if clean_headline and clean_url:
        return {"headline": clean_headline, "url": clean_url}
    return None


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


def _trim_payload(payload: Any) -> List[Dict[str, str]]:
    trimmed: List[Dict[str, str]] = []
    if not isinstance(payload, list):
        return trimmed
    for item in payload:
        if not isinstance(item, dict):
            continue
        news_item = _make_news_item(item.get("headline"), item.get("url"))
        if news_item is not None:
            trimmed.append(news_item)
    return trimmed


def _lookup_instrument_name(ticker: str) -> Optional[str]:
    """Best-effort lookup for a human friendly instrument name."""

    try:
        meta = get_instrument_meta(ticker)
    except Exception:  # pragma: no cover - defensive logging happens upstream
        return None

    if not isinstance(meta, dict):
        return None

    for key in ("name", "instrument_name", "display_name"):
        value = _clean_str(meta.get(key))
        if value:
            return value
    return None


def _build_fallback_query(ticker: str) -> tuple[str, Optional[str]]:
    """Return a finance-focused query string and optional instrument name."""

    tkr = ticker.strip().upper()
    instrument_name = _lookup_instrument_name(tkr)

    parts: List[str] = []
    if tkr:
        parts.append(tkr)
    if instrument_name:
        parts.append(instrument_name)
    parts.extend(["stock", "shares"])

    seen: set[str] = set()
    deduped: List[str] = []
    for part in parts:
        if part and part not in seen:
            deduped.append(part)
            seen.add(part)

    return (" ".join(deduped) if deduped else tkr), instrument_name


def _is_finance_related(headline: str, ticker: str, instrument_name: Optional[str]) -> bool:
    """Return True when ``headline`` appears relevant to the instrument."""

    text_lower = headline.lower()
    upper_headline = headline.upper()
    symbol = ticker.strip().upper()
    if symbol and symbol in upper_headline:
        return True

    if instrument_name:
        lowered_name = instrument_name.lower()
        if lowered_name and lowered_name in text_lower:
            return True

    return any(keyword in text_lower for keyword in _FINANCE_KEYWORDS)


def fetch_news_yahoo(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Yahoo Finance search API."""

    endpoint = cfg.yahoo_news_endpoint or "https://query1.finance.yahoo.com/v1/finance/search"
    clean_ticker = ticker.strip().upper()
    query, instrument_name = _build_fallback_query(clean_ticker)
    params = {"q": query, "quotesCount": 0, "newsCount": 10}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("news", [])
    out: List[Dict[str, str]] = []
    for item in items:
        news_item = _make_news_item(item.get("title"), item.get("link"))
        if news_item is not None and _is_finance_related(
            news_item["headline"], clean_ticker, instrument_name
        ):
            out.append(news_item)
    return out


def fetch_news_google(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Google Finance via RSS search."""

    endpoint = cfg.google_news_endpoint or "https://news.google.com/rss/search"
    clean_ticker = ticker.strip().upper()
    query, instrument_name = _build_fallback_query(clean_ticker)
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    resp = requests.get(endpoint, params=params, timeout=10)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        news_item = _make_news_item(item.findtext("title"), item.findtext("link"))
        if news_item is not None and _is_finance_related(
            news_item["headline"], clean_ticker, instrument_name
        ):
            out.append(news_item)
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
            enriched: List[Dict[str, str]] = []
            for item in feed:
                news_item = _make_news_item(item.get("title"), item.get("url"))
                if news_item is None:
                    continue
                enriched.append(news_item)
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
    cache_writer: Callable[[str, List[Dict[str, str]]], None] | None = None,
    raise_on_quota_exhausted: bool = False,
) -> List[Dict[str, str]]:
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

    def _call() -> List[Dict[str, str]]:
        if not _try_consume_quota():
            raise RuntimeError("news quota exceeded")
        return _fetch_news(tkr)

    def _schedule_refresh(initial_delay: float | None = None) -> None:
        page_cache.schedule_refresh(
            page,
            NEWS_TTL,
            _call,
            can_refresh=_can_request_news,
            initial_delay=initial_delay,
        )

    cached_raw = page_cache.load_cache(page)
    cached = _trim_payload(cached_raw) if cached_raw is not None else None
    cache_fresh = cached_raw is not None and not page_cache.is_stale(page, NEWS_TTL)

    if cache_fresh:
        delay = page_cache.time_until_stale(page, NEWS_TTL)
        _schedule_refresh(delay)
        return cached if cached is not None else []

    try:
        payload = _call()
    except RuntimeError:
        if cached is not None:
            _schedule_refresh()
            return cached
        _schedule_refresh()
        if raise_on_quota_exhausted:
            raise
        return []

    payload = _trim_payload(payload)
    if cache_writer is not None:
        cache_writer(page, payload)
    else:
        page_cache.save_cache(page, payload)

    _schedule_refresh(NEWS_TTL)
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
