from __future__ import annotations

"""Market overview endpoint aggregating indexes, sectors and headlines."""

import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

import requests
import yfinance as yf
from fastapi import APIRouter, Query

from backend import config_module
from backend.routes.news import get_cached_news

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

UK_SECTOR_ENDPOINT_DEFAULT = "https://www.londonstockexchange.com/api/sectors/ftse350"
US_SECTOR_ETFS = {
    "Materials": "XLB",
    "Energy": "XLE",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Technology": "XLK",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Real Estate": "XLRE",
    "Health Care": "XLV",
}


logger = logging.getLogger(__name__)


class IndexPayload(TypedDict):
    value: float
    change: float


class SectorPayload(TypedDict):
    sector: str
    change: float
    source: Literal["lse", "us_etf"]


def _fetch_indexes() -> Dict[str, IndexPayload]:
    tickers = yf.Tickers(" ".join(INDEX_SYMBOLS.values())).tickers
    out: Dict[str, IndexPayload] = {}
    for name, sym in INDEX_SYMBOLS.items():
        info = getattr(tickers.get(sym), "info", {})
        price = info.get("regularMarketPrice")
        change = info.get("regularMarketChangePercent")
        if price is not None:
            out[name] = {
                "value": float(price),
                "change": float(change) if change is not None else 0.0,
            }
    return out


def _fetch_sectors() -> List[SectorPayload]:
    params = {"function": "SECTOR", "apikey": cfg.alpha_vantage_key or "demo"}
    resp = requests.get("https://www.alphavantage.co/query", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("Rank A: Real-Time Performance", {})
    out: List[SectorPayload] = []
    invalid_payload = not isinstance(data, dict)
    for sector, change in data.items() if isinstance(data, dict) else []:
        try:
            out.append(
                {
                    "sector": sector,
                    "change": float(str(change).rstrip("%")),
                    "source": "lse",
                }
            )
        except Exception:
            continue

    if isinstance(data, dict) and data and not out:
        invalid_payload = True

    if out:
        return out

    if invalid_payload or not data:
        logger.warning(
            "Falling back to US sector ETF data because LSE sector payload is empty/invalid"
        )
    return _fetch_us_sector_etf_changes()


def _fetch_us_sector_etf_changes() -> List[SectorPayload]:
    """Fallback US sector performance based on SPDR sector ETF recent closes."""

    symbols = list(US_SECTOR_ETFS.values())
    prices = yf.download(symbols, period="2d", interval="1d", progress=False, auto_adjust=False)
    closes = prices.get("Close") if hasattr(prices, "get") else None
    if closes is None:
        logger.error("US sector ETF fallback returned no Close data")
        return []

    out: List[SectorPayload] = []
    for sector, symbol in US_SECTOR_ETFS.items():
        if symbol not in closes:
            logger.warning(
                "Skipping sector fallback for %s because %s close data is missing", sector, symbol
            )
            continue

        try:
            series = closes[symbol].dropna()
            if len(series) < 2:
                logger.warning(
                    "Skipping sector fallback for %s because %s has fewer than 2 closes",
                    sector,
                    symbol,
                )
                continue
            previous_close = float(series.iloc[-2])
            latest_close = float(series.iloc[-1])
            if previous_close == 0:
                logger.warning(
                    "Skipping sector fallback for %s because previous close is zero", sector
                )
                continue
            pct_change = ((latest_close - previous_close) / previous_close) * 100
            out.append({"sector": sector, "change": pct_change, "source": "us_etf"})
        except (TypeError, ValueError):
            logger.warning("Skipping sector fallback for %s due to invalid close data", sector)
            continue

    if not out:
        logger.error("Unable to compute sector ETF fallback changes; all symbols invalid/missing")
    return out


def _fetch_uk_sectors() -> List[SectorPayload]:
    """Fetch FTSE sector performance data from the London Stock Exchange API."""

    endpoint = getattr(cfg, "uk_sector_endpoint", None) or UK_SECTOR_ENDPOINT_DEFAULT
    headers: Dict[str, str] = {}
    user_agent = getattr(cfg, "selenium_user_agent", None)
    if user_agent:
        headers["User-Agent"] = user_agent

    resp = requests.get(endpoint, headers=headers, timeout=10)
    resp.raise_for_status()
    payload = resp.json()

    items: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in (
            "sectors",
            "sectorPerformance",
            "indexSectors",
            "items",
            "data",
            "constituents",
            "values",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            if all(isinstance(v, (int, float, str)) for v in payload.values()):
                items = [{"name": name, "percentChange": value} for name, value in payload.items()]
    elif isinstance(payload, list):
        items = payload

    out: List[SectorPayload] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue

        name = (
            entry.get("name")
            or entry.get("sector")
            or entry.get("sectorName")
            or entry.get("label")
        )
        if not name:
            continue

        change_raw: Any = (
            entry.get("percentChange")
            or entry.get("percentageChange")
            or entry.get("change")
            or entry.get("changePercent")
            or entry.get("changePercentage")
            or entry.get("pctChange")
        )

        if change_raw is None:
            if isinstance(entry.get("performance"), dict):
                perf = entry["performance"]
                for key in ("percentChange", "percentageChange", "change", "pct", "value"):
                    if perf.get(key) is not None:
                        change_raw = perf[key]
                        break
            elif isinstance(entry.get("values"), dict):
                values = entry["values"]
                for key in ("percentChange", "percentageChange", "change", "pct"):
                    if values.get(key) is not None:
                        change_raw = values[key]
                        break

        if isinstance(change_raw, str):
            change_raw = change_raw.strip().rstrip("%")

        try:
            change = float(change_raw)
        except (TypeError, ValueError):
            continue

        out.append({"sector": name, "change": change, "source": "lse"})

    return out


def _fetch_headlines() -> List[Dict[str, str]]:
    """Fetch latest headlines for all known index symbols.

    Each index symbol is queried individually; results are aggregated and
    de-duplicated by URL or headline.  If all requests fail, an error is logged
    so callers have some visibility into the failure.
    """

    logger = logging.getLogger(__name__)
    headlines: List[Dict[str, str]] = []
    seen: set[str] = set()
    success = False

    for sym in INDEX_SYMBOLS.values():
        try:
            items = get_cached_news(sym)
        except RuntimeError:
            logger.warning(
                "News quota exhausted while building market headlines; returning partial data"
            )
            break

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

    return headlines


def _safe(func, default):
    try:
        return func()
    except Exception:  # pragma: no cover - network errors
        return default


@router.get("/market/overview")
async def market_overview(
    region: Optional[str] = Query(None, description="Set to 'uk' to use London sector data.")
) -> Dict[str, Any]:
    """Return index levels, sector performance and latest headlines."""

    indexes = _safe(_fetch_indexes, {})
    default_region = getattr(cfg, "default_sector_region", "US") or "US"
    region_value = region if isinstance(region, str) else None
    selected_region = (region_value or default_region).lower()
    fetcher = _fetch_uk_sectors if selected_region == "uk" else _fetch_sectors
    sectors = _safe(fetcher, [])
    headlines = _safe(_fetch_headlines, [])
    return {"indexes": indexes, "sectors": sectors, "headlines": headlines}
