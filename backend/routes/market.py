from __future__ import annotations

"""Market overview endpoint aggregating indexes, sectors and headlines."""

import asyncio
import functools
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict

from fastapi import APIRouter, HTTPException, Query

from backend import config_module
from backend.common import market_sectors
from backend.common.yahoo_chart import chart_quote
from backend.logging_setup import sanitise_log_value
from backend.routes.news import NewsQuotaExceeded, get_cached_news
from backend.utils.lazy_import import lazy_import

# yfinance is only needed when market endpoints are called, not at import time.
yf = lazy_import("yfinance")

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

router = APIRouter(tags=["market"])

INDEX_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "NASDAQ": "^IXIC",
    "FTSE 100": "^FTSE",
    "FTSE 250": "^FTMC",
}


logger = logging.getLogger(__name__)

# Headlines older than this are excluded from the Market Overview feed so the
# page doesn't surface stale stories mixed in with recent ones.  Mirrors the
# staleness-threshold pattern used for cache freshness in
# ``backend.routes.news.NEWS_MAX_STALENESS``, but this applies to the
# article's own publish date rather than the cache's age.
DEFAULT_HEADLINE_MAX_AGE_HOURS = 72.0


def _get_headline_max_age() -> timedelta:
    """Return the configured headline age limit, or the safe default."""

    raw_hours = os.getenv("HEADLINE_MAX_AGE_HOURS")
    if raw_hours is None:
        return timedelta(hours=DEFAULT_HEADLINE_MAX_AGE_HOURS)

    try:
        hours = float(raw_hours)
    except ValueError:
        logger.warning(
            "Invalid HEADLINE_MAX_AGE_HOURS=%r; using the %.0f-hour default",
            sanitise_log_value(raw_hours),
            DEFAULT_HEADLINE_MAX_AGE_HOURS,
        )
        return timedelta(hours=DEFAULT_HEADLINE_MAX_AGE_HOURS)

    if not math.isfinite(hours) or hours <= 0:
        logger.warning(
            "HEADLINE_MAX_AGE_HOURS must be positive; using the %.0f-hour default",
            DEFAULT_HEADLINE_MAX_AGE_HOURS,
        )
        return timedelta(hours=DEFAULT_HEADLINE_MAX_AGE_HOURS)

    return timedelta(hours=hours)


# Read once at module import time: HEADLINE_MAX_AGE_HOURS is not re-read on
# each request, so changing the env var requires restarting the process for
# the new value to take effect.
HEADLINE_MAX_AGE = _get_headline_max_age()


class IndexPayload(TypedDict):
    value: float
    change: float
    # When the level was struck (ISO-8601, UTC), so the page can say how old
    # it is instead of leaving live and stale data indistinguishable (#7788).
    # Omitted when the provider gives no timestamp.
    as_of: NotRequired[str]


def _epoch_to_iso(epoch: Any) -> Optional[str]:
    """Return ``epoch`` seconds as an ISO-8601 UTC string, or ``None``."""

    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool) or epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _fetch_indexes() -> Dict[str, IndexPayload]:
    tickers = yf.Tickers(" ".join(INDEX_SYMBOLS.values())).tickers
    out: Dict[str, IndexPayload] = {}
    for name, sym in INDEX_SYMBOLS.items():
        ticker = tickers.get(sym)
        if ticker is None:
            continue
        # Chart endpoint, not ``.info``: ``quoteSummary`` fails with
        # ``401 Invalid Crumb`` when Yahoo rejects yfinance's crumb handshake.
        info = chart_quote(ticker)
        price = info.get("regularMarketPrice")
        change = info.get("regularMarketChangePercent")
        if price is not None:
            payload: IndexPayload = {
                "value": float(price),
                "change": float(change) if change is not None else 0.0,
            }
            as_of = _epoch_to_iso(info.get("regularMarketTime"))
            if as_of is not None:
                payload["as_of"] = as_of
            out[name] = payload
    return out


def _fetch_index_period_changes(period: market_sectors.Period) -> Dict[str, IndexPayload]:
    """Return each index's latest close and % change over ``period``.

    Multi-day periods come from daily closes rather than the live chart
    quote, so ``value`` is the last close, not an intraday level.
    """

    history = market_sectors.download_period_history(list(INDEX_SYMBOLS.values()), period)
    out: Dict[str, IndexPayload] = {}
    for name, sym in INDEX_SYMBOLS.items():
        change = market_sectors.period_change(market_sectors.series_for(history.total_return, sym), period)
        if change is None:
            logger.warning(
                "No %s index change for %s: close data missing", sanitise_log_value(period), sanitise_log_value(sym)
            )
            continue
        # The level shown is the traded close, not the reinvested index.
        traded = market_sectors.series_for(history.traded, sym)
        payload: IndexPayload = {"value": float(traded.iloc[-1]), "change": change}
        as_of = _index_label_to_iso(traded.index[-1])
        if as_of is not None:
            payload["as_of"] = as_of
        out[name] = payload
    return out


def _index_label_to_iso(label: Any) -> Optional[str]:
    """Return a close's date label as ISO-8601, or ``None`` if it isn't a date."""

    isoformat = getattr(label, "isoformat", None)
    return isoformat() if callable(isoformat) else None


def _parse_published_at(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 ``published_at`` string into a timezone-aware datetime."""

    if not isinstance(value, str) or not value:
        return None

    cleaned = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sort_and_filter_headlines(headlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort headlines newest-first and drop ones older than ``HEADLINE_MAX_AGE``.

    Items whose ``published_at`` is missing or unparsable are treated as
    undated: they're excluded from the primary (recency-filtered) result but
    kept as a fallback, sorted after any dated items, so the page still shows
    something when upstream providers return sparse or undated coverage
    instead of going to an empty state.
    """

    now = datetime.now(timezone.utc)
    dated: List[tuple[datetime, Dict[str, Any]]] = []
    undated: List[Dict[str, Any]] = []

    for item in headlines:
        published = _parse_published_at(item.get("published_at"))
        if published is None:
            undated.append(item)
        else:
            dated.append((published, item))

    dated.sort(key=lambda pair: pair[0], reverse=True)
    recent = [item for published, item in dated if now - published <= HEADLINE_MAX_AGE]

    if recent:
        return recent

    return [item for _, item in dated] + undated


HeadlineStatus = Literal["ok", "quota_exhausted", "unavailable"]


class HeadlineList(List[Dict[str, Any]]):
    """Headlines plus why the list is what it is.

    A plain ``list`` subclass so existing callers and tests that compare it to
    a list keep working; ``status`` lets the page tell "no news source
    answered" apart from "the provider quota ran out" instead of one bare
    "No headlines available" (#7788 item 13).
    """

    def __init__(self, items: List[Dict[str, Any]], status: HeadlineStatus) -> None:
        super().__init__(items)
        self.status: HeadlineStatus = status


def _headline_status(headlines: List[Dict[str, Any]]) -> HeadlineStatus:
    """Return the status for ``headlines``, defaulting plain lists by emptiness."""

    status = getattr(headlines, "status", None)
    if status is not None:
        return status
    return "ok" if headlines else "unavailable"


def _fetch_headlines() -> HeadlineList:
    """Fetch latest headlines for all known index symbols.

    Each index symbol is queried individually; results are aggregated and
    de-duplicated by URL or headline, then sorted newest-first and filtered
    to ``HEADLINE_MAX_AGE`` (see ``_sort_and_filter_headlines``).  Each item
    carries the ``stale`` flag from ``get_cached_news`` so the frontend can
    flag headlines served from an aged cache.  If all requests fail, an error
    is logged so callers have some visibility into the failure.
    """

    logger = logging.getLogger(__name__)
    headlines: List[Dict[str, Any]] = []
    seen: set[str] = set()
    success = False
    quota_exhausted = False
    # Some symbol's lookup completed without an error, even if it found
    # nothing: an empty feed is then a quiet day, not a dead source (#7788).
    answered = False

    for sym in INDEX_SYMBOLS.values():
        try:
            # Raise rather than return [] on exhaustion, so the page can say
            # the quota ran out; a symbol with a cached payload still returns it.
            items = get_cached_news(sym, raise_on_quota_exhausted=True)
        except NewsQuotaExceeded:
            logger.warning("News quota exhausted for %s; skipping it", sanitise_log_value(sym))
            quota_exhausted = True
            continue
        except Exception:
            # One failing symbol must not blank the whole headline list, and
            # an unexpected error must not masquerade as quota exhaustion.
            logger.exception("Failed to fetch news for %s", sanitise_log_value(sym))
            continue

        answered = True
        if not items:
            continue

        success = True
        for item in items:
            key = item.get("url") or item.get("headline")
            if key and key not in seen:
                seen.add(key)
                headlines.append(item)

    if not success:
        logger.error("Failed to fetch news for all index symbols")

    return HeadlineList(
        _sort_and_filter_headlines(headlines),
        _empty_or_ok_status(success, quota_exhausted, answered),
    )


def _empty_or_ok_status(success: bool, quota_exhausted: bool, answered: bool) -> HeadlineStatus:
    """Status for a headline fetch: ``ok`` unless the feed is empty for a known reason.

    An empty feed after the quota ran out is ``quota_exhausted``; one where no
    symbol's lookup completed is ``unavailable``. Otherwise a source answered
    with nothing (a quiet day), which is ``ok`` with no headlines.
    """

    if success:
        return "ok"
    if quota_exhausted:
        return "quota_exhausted"
    return "ok" if answered else "unavailable"


def _safe(func, default):
    try:
        return func()
    except Exception:  # pragma: no cover - network errors
        return default


@router.get("/market/overview")
async def market_overview(
    region: Optional[str] = Query(
        None, description="Sector region: global, us or uk; defaults to default_sector_region."
    ),
    sectors: bool = Query(
        True,
        description="Set to false to skip sector data, e.g. when the caller loads it from /market/sectors.",
    ),
) -> Dict[str, Any]:
    """Return index levels, sector performance and latest headlines."""

    # Called directly (not via FastAPI), unset params are ``Query`` objects.
    region_value = region if isinstance(region, str) else None
    # Unlike /market/sectors, an unknown region here falls back to the
    # default rather than failing the whole overview.
    selected = market_sectors.normalise_region(region_value) or _default_region()
    if sectors is False:
        fetcher = _no_sectors
    else:
        fetcher = functools.partial(market_sectors.fetch_region_sectors, selected)

    # Each fetcher does blocking network I/O, so run them on the default
    # executor's thread pool and await them together instead of one after
    # another - total latency becomes roughly the slowest fetcher instead of
    # the sum of all three. `_safe` still runs inside each thread, so an
    # exception in one fetcher only replaces that fetcher's own result with
    # its default and doesn't affect the others or fail the gather.
    #
    # `run_in_executor(None, ...)` uses the event loop's *default* executor,
    # a single process-wide `ThreadPoolExecutor` shared by every coroutine in
    # this process that doesn't pass its own executor. Under concurrent
    # traffic, requests here compete for the same worker threads as any other
    # blocking work offloaded elsewhere in the app - a burst of slow fetchers
    # can starve unrelated `run_in_executor(None, ...)` calls of workers. If
    # this becomes a bottleneck, give this route (or the app) a dedicated
    # `ThreadPoolExecutor` instead of relying on the shared default.
    loop = asyncio.get_running_loop()
    indexes, sector_rows, headlines = await asyncio.gather(
        loop.run_in_executor(None, _safe, _fetch_indexes, {}),
        loop.run_in_executor(None, _safe, fetcher, []),
        loop.run_in_executor(None, _safe, _fetch_headlines, []),
    )
    return {
        "indexes": indexes,
        "sectors": sector_rows,
        "headlines": headlines,
        "headlines_status": _headline_status(headlines),
    }


def _no_sectors() -> List[market_sectors.RegionSector]:
    return []


def _default_region() -> market_sectors.Region:
    """Return the configured sector region, or ``us`` if it's missing/unknown."""

    return market_sectors.normalise_region(getattr(cfg, "default_sector_region", None)) or "us"


def _resolve_period(period: Optional[str]) -> market_sectors.Period:
    """Map the ``period`` query value to a canonical period (default ``1D``)."""

    if period is None:
        return "1D"
    resolved = market_sectors.normalise_period(period)
    if resolved is None:
        allowed = ", ".join(market_sectors.PERIODS)
        raise HTTPException(status_code=400, detail=f"Unknown period; expected one of: {allowed}")
    return resolved


PERIOD_QUERY_DESCRIPTION = "Change window: 1D, 1W, 1M (30 days), 3M (90 days) or 1Y; defaults to 1D."


def _resolve_region(region: Optional[str]) -> market_sectors.Region:
    """Map the query value (or the configured default) to a sector region.

    An explicit unknown value is a client error; an unknown configured default
    falls back to ``us`` so a bad config can't take the page down.
    """

    if region is not None:
        resolved = market_sectors.normalise_region(region)
        if resolved is None:
            allowed = ", ".join(market_sectors.REGIONS)
            raise HTTPException(status_code=400, detail=f"Unknown region; expected one of: {allowed}")
        return resolved
    return _default_region()


@router.get("/market/indexes")
async def market_indexes(
    period: Optional[str] = Query(None, description=PERIOD_QUERY_DESCRIPTION),
) -> Dict[str, Any]:
    """Return each headline index's level and % change over ``period``."""

    resolved = _resolve_period(period)
    # 1D keeps the live chart quote the overview uses, so both agree.
    fetcher = _fetch_indexes if resolved == "1D" else functools.partial(_fetch_index_period_changes, resolved)
    loop = asyncio.get_running_loop()
    try:
        indexes = await loop.run_in_executor(None, fetcher)
    except Exception as exc:
        logger.exception("Index fetch failed for period %s", sanitise_log_value(resolved))
        raise HTTPException(status_code=502, detail="Index data is unavailable") from exc
    return {"period": resolved, "indexes": indexes}


@router.get("/market/sectors")
async def market_sectors_by_region(
    region: Optional[str] = Query(None, description="global, us or uk; defaults to default_sector_region."),
    period: Optional[str] = Query(None, description=PERIOD_QUERY_DESCRIPTION),
) -> Dict[str, Any]:
    """Return the % change per GICS sector for one region over ``period``."""

    resolved = _resolve_region(region)
    resolved_period = _resolve_period(period)
    loop = asyncio.get_running_loop()
    try:
        rows = await loop.run_in_executor(None, market_sectors.fetch_region_sectors, resolved, resolved_period)
    except Exception as exc:
        logger.exception(
            "Sector fetch failed for region %s period %s",
            sanitise_log_value(resolved),
            sanitise_log_value(resolved_period),
        )
        raise HTTPException(status_code=502, detail="Sector data is unavailable") from exc
    return {"region": resolved, "period": resolved_period, "sectors": rows}


@router.get("/market/sectors/{region}/{sector}")
async def market_sector_detail(region: str, sector: str) -> Dict[str, Any]:
    """Return returns, recent history and representative constituents for a sector."""

    resolved = market_sectors.normalise_region(region)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Unknown region")
    name = market_sectors.find_sector(resolved, sector)
    if name is None:
        raise HTTPException(status_code=404, detail="No detail available for this sector")
    loop = asyncio.get_running_loop()
    try:
        detail = await loop.run_in_executor(None, market_sectors.fetch_sector_detail, resolved, name)
    except Exception as exc:
        logger.exception("Sector detail fetch failed for %s/%s", sanitise_log_value(resolved), sanitise_log_value(name))
        raise HTTPException(status_code=502, detail="Sector data is unavailable") from exc
    return dict(detail)
