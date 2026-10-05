"""Simple news retrieval endpoint."""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
from concurrent.futures import Future
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import defusedxml.ElementTree as ET
import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from backend import config_module
from backend.common.instruments import _build_yahoo_symbol, get_instrument_meta
from backend.common.url_validator import validate_external_url
from backend.logging_setup import sanitise_log_value
from backend.utils import page_cache
from backend.utils.lazy_import import lazy_import

# Only needed for the Yahoo fallback, so keep it off the import path
# (Lambda cold start), matching how ``market.py`` loads yfinance.
curl_requests = lazy_import("curl_cffi.requests")

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

router = APIRouter(tags=["news"])

NEWS_TTL = 900  # seconds
# Serving cached news older than this (in seconds) is treated as a fault worth
# surfacing: it means live fetches have not succeeded for far longer than the
# normal refresh interval (``NEWS_TTL``) and the user is seeing stale stories.
NEWS_MAX_STALENESS = 24 * 60 * 60  # 1 day
BASE_URL = "https://www.alphavantage.co/query"
COUNTER_FILE: Path = page_cache.CACHE_DIR / "news_requests.json"
# Yahoo rate-limits (429) requests that don't look like a browser, which
# plain ``requests`` (``python-requests/x.y`` UA, non-browser TLS fingerprint)
# triggers almost immediately. ``curl_cffi`` impersonates Chrome's TLS and
# HTTP/2 fingerprint, the same approach yfinance uses for its own calls.
YAHOO_IMPERSONATE = "chrome"
# After a 429, skip Yahoo for this long (or for the response's numeric
# ``Retry-After``, capped at ``YAHOO_COOLDOWN_MAX``). Retrying straight away,
# once per ticker, only keeps the IP flagged.
YAHOO_COOLDOWN_DEFAULT = 300  # seconds
YAHOO_COOLDOWN_MAX = 3600  # seconds
# AlphaVantage answers with one of these keys instead of ``feed`` when the key
# is invalid, rate-limited, or (for ``demo``) not entitled to the ticker.
_ALPHA_NOTICE_KEYS = ("Information", "Note", "Error Message")

# Per-ticker in-flight fetches, so concurrent callers for the same ticker
# share one upstream fetch (and one quota unit) instead of each hitting the
# providers. Entries exist only while a fetch is running.
_inflight_lock = threading.Lock()
_inflight: Dict[str, "Future[List[Dict[str, str]]]"] = {}

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


def _make_news_item(
    headline: object,
    url: object,
    published_at: object = None,
    source: object = None,
) -> Dict[str, str] | None:
    """Return a news item when both ``headline`` and ``url`` are valid.

    ``published_at`` (an already-normalised ISO-8601 string) and ``source`` are
    optional and only included when present, so callers that lack them still
    produce the minimal ``{"headline", "url"}`` shape.
    """

    clean_headline = _clean_str(headline)
    clean_url = _clean_str(url)
    if not (clean_headline and clean_url):
        return None

    item: Dict[str, str] = {"headline": clean_headline, "url": clean_url}
    clean_published = _clean_str(published_at)
    if clean_published:
        item["published_at"] = clean_published
    clean_source = _clean_str(source)
    if clean_source:
        item["source"] = clean_source
    return item


class NewsQuotaExceeded(RuntimeError):
    """Raised when no news provider can make a request today."""


# Providers that spent quota (made a request) during the current
# ``_fetch_news`` call; ``None`` outside one.
_spent_quota: ContextVar[Optional[List[str]]] = ContextVar("_news_spent_quota", default=None)


class _ProviderQuota:
    """Daily request budget for one news provider, persisted to a JSON file.

    Each provider spends its own budget, and only when it actually makes a
    request: a provider that is skipped (no AlphaVantage key, Yahoo cooling
    down after a 429) costs nothing. ``news_requests_per_day`` (25) matches
    AlphaVantage's free tier; Yahoo and Google have their own limits.
    """

    def __init__(self, name: str, limit_attr: str, default_limit: int, file_suffix: str = "") -> None:
        self.name = name
        self._limit_attr = limit_attr
        self._default_limit = default_limit
        self._file_suffix = file_suffix
        # Serialises read-modify-write across the executor threads that run
        # concurrent fetches (not across processes).
        self._lock = threading.Lock()
        # Date exhaustion was last announced at INFO, so a provider out of
        # budget logs once a day rather than once per skipped fetch.
        self._exhaustion_logged_on: Optional[str] = None

    @property
    def path(self) -> Path:
        # Derived from ``COUNTER_FILE`` at call time so tests can redirect it.
        if not self._file_suffix:
            return COUNTER_FILE
        return COUNTER_FILE.with_name(f"{COUNTER_FILE.stem}_{self._file_suffix}{COUNTER_FILE.suffix}")

    @property
    def limit(self) -> int:
        value = getattr(cfg, self._limit_attr, None)
        return int(value) if value is not None else self._default_limit

    def load(self) -> Dict[str, Any]:
        today = date.today().isoformat()
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("date") == today:
                return {"date": today, "count": int(data.get("count", 0))}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            logging.getLogger(__name__).warning(
                "Resetting unreadable %s news quota counter: %s", self.name, sanitise_log_value(exc)
            )
        return {"date": today, "count": 0}

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def available(self) -> bool:
        return self.load()["count"] < self.limit

    def _log_exhausted(self, today: str) -> None:
        """Log a skip for an exhausted budget: INFO once per day, then DEBUG."""

        level = logging.DEBUG if self._exhaustion_logged_on == today else logging.INFO
        self._exhaustion_logged_on = today
        logging.getLogger(__name__).log(
            level,
            "%s news quota exhausted for today (limit %d); skipping %s until tomorrow",
            self.name,
            self.limit,
            self.name,
        )

    def try_consume(self) -> bool:
        """Spend one request if any remain today; return whether it was spent."""

        with self._lock:
            data = self.load()
            if data["count"] >= self.limit:
                self._log_exhausted(data["date"])
                return False
            data["count"] += 1
            self.save(data)
        spent = _spent_quota.get()
        if spent is not None:
            spent.append(self.name)
        return True


_ALPHA_QUOTA = _ProviderQuota("AlphaVantage", "news_requests_per_day", 25)
_YAHOO_QUOTA = _ProviderQuota("Yahoo", "yahoo_news_requests_per_day", 500, "yahoo")
_GOOGLE_QUOTA = _ProviderQuota("Google", "google_news_requests_per_day", 500, "google")


def _can_request_news() -> bool:
    """Return whether at least one provider could make a request right now."""

    alpha = bool(cfg.alpha_vantage_key) and _ALPHA_QUOTA.available()
    yahoo = _yahoo_cooldown.remaining() <= 0 and _YAHOO_QUOTA.available()
    return alpha or yahoo or _GOOGLE_QUOTA.available()


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
        news_item = _make_news_item(
            item.get("headline"),
            item.get("url"),
            item.get("published_at"),
            item.get("source"),
        )
        if news_item is not None:
            trimmed.append(news_item)
    return _sort_by_published_at_desc(trimmed)


def _sort_by_published_at_desc(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Return ``items`` ordered most-recent-first by ``published_at``.

    ``published_at`` values are already normalised to ISO-8601 UTC strings by
    ``_isoformat``, so lexicographic ordering matches chronological ordering.
    Items missing ``published_at`` sort last rather than being dropped, since
    upstream sources (notably the Yahoo/Google fallbacks) don't always return
    results in date order.
    """

    return sorted(items, key=lambda item: item.get("published_at") or "", reverse=True)


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


# Exchange codes this app appends to tickers (``ADBE.N``, ``AZN.L``); see
# ``backend.common.instruments._yahoo_suffix_for_exchange``.
_EXCHANGE_CODES = frozenset(
    {"L", "LSE", "UK", "N", "NYSE", "O", "NASDAQ", "US", "PA", "PARIS", "DE", "XETRA", "TO", "TSX", "AX", "ASX", "F"}
)
# Instrument-master names carry share-class and par-value noise after the
# company name ("Adobe Inc Comm Stk US$.0001 *R"); cut at the first of these.
_SHARE_CLASS_TOKENS = frozenset({"class", "cl", "ord", "ordinary", "shs", "stk", "npv", "adr", "ads", "cdi", "reg"})
_COMMON_STOCK_PREFIXES = frozenset({"com", "comm", "common"})
_COMMON_STOCK_SUFFIXES = frozenset({"stk", "stock", "shs", "shares"})
# Par values: "US$0.01", "$.0001", "GBP0.25", "0.25", and UK pence such as
# "10p". A bare integer is not one: "S&P 500" and "FTSE 100" are names.
_PAR_VALUE = re.compile(
    r"^(?:US\$|\$|£|€|GBP|GBX|USD|EUR)\d*\.?\d+p?$|^\d*\.\d+p?$|^\d+p$|^US\$",
    re.IGNORECASE,
)
_LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "corp",
        "corporation",
        "plc",
        "p.l.c",
        "ltd",
        "limited",
        "co",
        "company",
        "sa",
        "ag",
        "nv",
        "se",
        "llc",
        "lp",
    }
)


@dataclass(frozen=True)
class _NewsSubject:
    """The instrument a news search is about, in the forms each provider needs."""

    symbol: str
    exchange: Optional[str]
    name: Optional[str]


def _split_ticker(ticker: str) -> tuple[str, Optional[str]]:
    """Split ``ADBE.N`` into ``("ADBE", "N")``; leave ``^FTSE``/``PFE`` whole."""

    tkr = ticker.strip().upper()
    symbol, sep, exchange = tkr.rpartition(".")
    if sep and symbol and exchange in _EXCHANGE_CODES:
        return symbol, exchange
    return tkr, None


def _cut_share_class_noise(tokens: List[str]) -> List[str]:
    for idx, token in enumerate(tokens):
        lower = token.lower().strip(".,")
        following = tokens[idx + 1].lower().strip(".,") if idx + 1 < len(tokens) else ""
        if (
            lower in _SHARE_CLASS_TOKENS
            or (lower in _COMMON_STOCK_PREFIXES and following in _COMMON_STOCK_SUFFIXES)
            or _PAR_VALUE.match(token)
        ):
            return tokens[:idx]
    return tokens


def _normalise_instrument_name(name: Optional[str]) -> Optional[str]:
    """Reduce an instrument-master name to the company name used in headlines.

    ``"Adobe Inc Comm Stk US$.0001 *R"`` -> ``"Adobe"``;
    ``"Alphabet Inc. (Class A)"`` -> ``"Alphabet"``.
    """

    if not name:
        return None
    text = re.sub(r"\([^)]*\)", " ", html.unescape(name))
    tokens = [token for token in text.split() if not token.startswith("*")]
    tokens = _cut_share_class_noise(tokens)
    while tokens and tokens[-1].lower().strip(".,") in _LEGAL_SUFFIXES:
        tokens.pop()
    cleaned = " ".join(tokens).strip(" ,.-")
    return cleaned or None


def _news_subject(ticker: str) -> _NewsSubject:
    symbol, exchange = _split_ticker(ticker)
    name = _normalise_instrument_name(_lookup_instrument_name(ticker.strip().upper()))
    return _NewsSubject(symbol=symbol, exchange=exchange, name=name)


def _google_query(subject: _NewsSubject) -> str:
    """``"Adobe" OR ADBE stock``: either identifier, anchored to finance."""

    symbol = subject.symbol.lstrip("^")
    if subject.name and subject.name.upper() != symbol:
        return f'"{subject.name}" OR {symbol} stock'
    return f"{symbol} stock"


def _yahoo_query(subject: _NewsSubject) -> str:
    """Yahoo's search resolves its own symbols best (``ADBE``, ``AZN.L``)."""

    if subject.exchange is None:
        return subject.symbol
    try:
        return _build_yahoo_symbol(subject.symbol, subject.exchange)
    except ValueError:
        return subject.symbol


def _alpha_ticker(ticker: str) -> str:
    """AlphaVantage form of ``ticker`` (``ADBE.N`` -> ``ADBE``, ``AZN.L`` -> ``AZN.LON``)."""

    symbol, exchange = _split_ticker(ticker)
    if exchange is None:
        return symbol
    # Deferred: the timeseries module imports pandas, which news otherwise avoids.
    from backend.timeseries.fetch_alphavantage_timeseries import _build_symbol

    return _build_symbol(symbol, exchange)


def _is_finance_related(headline: str, subject: _NewsSubject) -> bool:
    """Return True when ``headline`` appears relevant to the instrument."""

    symbol = subject.symbol.lstrip("^")
    # Case-sensitive on purpose: tickers that are also words ("IT", "ALL",
    # "ON") would otherwise match ordinary prose in almost every headline.
    if symbol and re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])", headline):
        return True

    text_lower = headline.lower()
    if subject.name and subject.name.lower() in text_lower:
        return True

    return any(keyword in text_lower for keyword in _FINANCE_KEYWORDS)


class _ProviderCooldown:
    """Thread-safe "don't call this provider until" deadline."""

    def __init__(self, default_seconds: int, max_seconds: int) -> None:
        self._default = default_seconds
        self._max = max_seconds
        self._until = 0.0
        # Deadline whose first skip has been announced; a new or extended
        # cooldown has a different deadline, so its first skip is announced too.
        self._announced_until = 0.0
        self._lock = threading.Lock()

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._until - time.monotonic())

    def trip(self, retry_after: object = None) -> int:
        """Start (or extend) the cooldown and return its length in seconds."""

        seconds = self._default
        if isinstance(retry_after, str) and retry_after.strip().isdigit():
            seconds = min(int(retry_after.strip()), self._max)
        with self._lock:
            self._until = max(self._until, time.monotonic() + seconds)
        return seconds

    def claim_first_skip(self) -> bool:
        """Return True for the first skip of the current cooldown, else False."""

        with self._lock:
            if self._announced_until == self._until:
                return False
            self._announced_until = self._until
            return True


_yahoo_cooldown = _ProviderCooldown(YAHOO_COOLDOWN_DEFAULT, YAHOO_COOLDOWN_MAX)


def fetch_news_yahoo(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Yahoo Finance search API.

    Returns ``[]`` without calling Yahoo while a 429 cooldown is active, and
    starts one when Yahoo answers 429, so callers fall through to the next
    provider instead of hammering a host that is already throttling us.
    """

    endpoint = cfg.yahoo_news_endpoint or "https://query1.finance.yahoo.com/v1/finance/search"
    validate_external_url(endpoint)
    remaining = _yahoo_cooldown.remaining()
    if remaining > 0:
        # INFO for the first skip of each cooldown, DEBUG for the rest.
        level = logging.INFO if _yahoo_cooldown.claim_first_skip() else logging.DEBUG
        logging.getLogger(__name__).log(
            level,
            "Skipping Yahoo news for %s: rate-limit cooldown, %d seconds left",
            sanitise_log_value(ticker),
            int(remaining),
        )
        return []
    if not _YAHOO_QUOTA.try_consume():
        return []
    clean_ticker = ticker.strip().upper()
    subject = _news_subject(clean_ticker)
    params = {"q": _yahoo_query(subject), "quotesCount": 0, "newsCount": 10}
    resp = curl_requests.get(
        endpoint,
        params=params,
        timeout=10,
        allow_redirects=False,
        impersonate=YAHOO_IMPERSONATE,
    )
    if resp.status_code == 429:
        seconds = _yahoo_cooldown.trip(resp.headers.get("Retry-After"))
        logging.getLogger(__name__).warning(
            "Yahoo news rate-limited (429) for %s; skipping Yahoo for %d seconds",
            sanitise_log_value(clean_ticker),
            seconds,
        )
        return []
    resp.raise_for_status()
    data = resp.json()
    items = data.get("news", [])
    out: List[Dict[str, str]] = []
    for item in items:
        news_item = _make_news_item(
            item.get("title"),
            item.get("link"),
            _parse_epoch_time(item.get("providerPublishTime")),
            item.get("publisher"),
        )
        if news_item is not None and _is_finance_related(news_item["headline"], subject):
            out.append(news_item)
    return out


def fetch_news_google(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from Google Finance via RSS search."""

    endpoint = cfg.google_news_endpoint or "https://news.google.com/rss/search"
    validate_external_url(endpoint)
    if not _GOOGLE_QUOTA.try_consume():
        return []
    clean_ticker = ticker.strip().upper()
    subject = _news_subject(clean_ticker)
    params = {"q": _google_query(subject), "hl": "en-US", "gl": "US", "ceid": "US:en"}
    resp = requests.get(endpoint, params=params, timeout=10, allow_redirects=False)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: List[Dict[str, str]] = []
    for item in root.findall(".//item"):
        news_item = _make_news_item(
            item.findtext("title"),
            item.findtext("link"),
            _parse_rss_time(item.findtext("pubDate")),
            item.findtext("source"),
        )
        if news_item is not None and _is_finance_related(news_item["headline"], subject):
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


def _parse_epoch_time(value: object) -> Optional[str]:
    """Convert a Unix epoch timestamp (Yahoo ``providerPublishTime``) to ISO."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return _isoformat(dt)


def _parse_rss_time(value: Optional[str]) -> Optional[str]:
    """Convert an RSS ``pubDate`` (RFC 822) string to ISO-8601."""

    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return _isoformat(dt)


def _log_alpha_notice(ticker: str, data: Dict[str, Any]) -> None:
    """Log AlphaVantage's explanation when it returns a notice instead of a feed."""

    for key in _ALPHA_NOTICE_KEYS:
        message = data.get(key)
        if message:
            logging.getLogger(__name__).warning(
                "AlphaVantage returned no news feed for %s (%s): %s",
                sanitise_log_value(ticker),
                key,
                sanitise_log_value(message),
            )
            return


# Set once the missing-key skip has been announced at INFO; cleared when a key
# is seen, so removing it again (config reload) is announced again.
_missing_alpha_key_logged = threading.Event()


def _log_missing_alpha_key(ticker: str) -> None:
    """Log the no-key skip at INFO once per process, then DEBUG.

    The key is static configuration, so one INFO line says why AlphaVantage
    isn't used without repeating it for every fetch.
    """

    if _missing_alpha_key_logged.is_set():
        logging.getLogger(__name__).debug(
            "Skipping AlphaVantage news for %s: no API key configured", sanitise_log_value(ticker)
        )
        return
    _missing_alpha_key_logged.set()
    logging.getLogger(__name__).info(
        "AlphaVantage news disabled: no API key configured (set ALPHA_VANTAGE_KEY); using Yahoo and Google"
    )


def fetch_news_alpha(ticker: str) -> List[Dict[str, str]]:
    """Fetch headlines from AlphaVantage ``NEWS_SENTIMENT``.

    Returns ``[]`` without a request when no API key is configured: the
    ``demo`` key only serves ``IBM``, so calling it for anything else always
    wastes a round trip before the fallbacks run.
    """

    if not cfg.alpha_vantage_key:
        _log_missing_alpha_key(ticker)
        return []
    _missing_alpha_key_logged.clear()
    if not _ALPHA_QUOTA.try_consume():
        return []
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": _alpha_ticker(ticker),
        "sort": "LATEST",
        "apikey": cfg.alpha_vantage_key,
    }
    resp = requests.get(BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    feed = data.get("feed") or []
    if not feed:
        _log_alpha_notice(ticker, data)
        return []
    enriched: List[Dict[str, str]] = []
    for item in feed:
        news_item = _make_news_item(
            item.get("title"),
            item.get("url"),
            _parse_alpha_time(item.get("time_published")),
            item.get("source"),
        )
        if news_item is not None:
            enriched.append(news_item)
    return enriched


def _fetch_news(ticker: str) -> List[Dict[str, str]]:
    """Fetch news from AlphaVantage with fallbacks to Yahoo and Google.

    Raises ``NewsQuotaExceeded`` when no provider made a request. The
    ``_can_request_news`` gate is checked before the chain runs, but another
    fetch can take the last unit of a provider's budget in between; without
    this check that race would come back as an empty result (and be cached
    as one) instead of as quota exhaustion.
    """

    spent: List[str] = []
    token = _spent_quota.set(spent)
    try:
        items = _fetch_from_providers(ticker)
    finally:
        _spent_quota.reset(token)
    if not items and not spent:
        logging.getLogger(__name__).info(
            "No news provider had quota left for %s by the time it ran", sanitise_log_value(ticker)
        )
        raise NewsQuotaExceeded("news quota exceeded")
    return items


def _fetch_from_providers(ticker: str) -> List[Dict[str, str]]:
    """Run the provider chain, returning the first non-empty result."""

    try:
        items = fetch_news_alpha(ticker)
        if items:
            return items
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).error(
            "Failed to fetch news for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc)
        )

    for fetcher in (fetch_news_yahoo, fetch_news_google):
        try:
            items = fetcher(ticker)
            if items:
                return items
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).error(
                "Fallback news fetch failed for %s: %s", sanitise_log_value(ticker), sanitise_log_value(exc)
            )
    return []


def _single_flight(key: str, fetch: Callable[[], List[Dict[str, str]]]) -> List[Dict[str, str]]:
    """Run ``fetch`` once per ``key`` across concurrent callers.

    The first caller for ``key`` runs ``fetch``; callers arriving while it is
    still running block on its result (or its exception) instead of starting
    their own upstream request. Once it finishes the entry is dropped, so a
    later call fetches again. This only covers the in-flight window: callers
    that arrive after it but before the cache file is written (``/news``
    persists via a background task) will still fetch.
    """

    with _inflight_lock:
        future = _inflight.get(key)
        is_leader = future is None
        if future is None:
            future = Future()
            _inflight[key] = future

    if not is_leader:
        return future.result()

    try:
        result = fetch()
    except BaseException as exc:
        future.set_exception(exc)
        raise
    else:
        future.set_result(result)
        return result
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)


def _is_cache_stale(page: str) -> bool:
    """Return True when the cache for ``page`` exceeds ``NEWS_MAX_STALENESS``."""

    age = page_cache.cache_age(page)
    return age is not None and age > NEWS_MAX_STALENESS


def _warn_if_stale(page: str) -> None:
    """Log a warning when the cache being served is dangerously old.

    Silently re-serving a months-old payload (e.g. because live fetches keep
    failing or the quota is perpetually exhausted) is exactly the failure mode
    reported in issue #4708.  Surfacing it in the logs gives operators a signal
    instead of the data ageing invisibly.
    """

    age = page_cache.cache_age(page)
    if age is not None and age > NEWS_MAX_STALENESS:
        logging.getLogger(__name__).warning(
            "Serving stale cached news for %s: cache is %d seconds old "
            "(threshold %d); live fetch has not succeeded recently",
            sanitise_log_value(page),
            int(age),
            NEWS_MAX_STALENESS,
        )


def _tag_stale(items: List[Dict[str, Any]], stale: bool) -> List[Dict[str, Any]]:
    """Return a copy of ``items`` with a ``stale`` flag attached to each.

    ``stale`` reflects whether the cache backing ``items`` exceeds
    ``NEWS_MAX_STALENESS``, so the frontend can flag headlines it would
    otherwise silently re-serve during a quota outage or fetch failure.
    """

    return [{**item, "stale": stale} for item in items]


def get_cached_news(
    ticker: str,
    *,
    cache_writer: Callable[[str, List[Dict[str, str]]], None] | None = None,
    raise_on_quota_exhausted: bool = False,
) -> List[Dict[str, Any]]:
    """Return cached or freshly fetched news for ``ticker``.

    Each returned item carries a ``stale`` flag (True when the cache backing
    it exceeds ``NEWS_MAX_STALENESS``) so callers can surface staleness to
    users instead of silently re-serving an old payload.

    The helper mirrors the caching and quota handling used by the ``/news``
    endpoint so that other modules can reuse the same logic synchronously.
    When ``cache_writer`` is provided it is invoked to persist fresh payloads;
    otherwise the helper writes to ``page_cache`` directly.  If the quota is
    exhausted and no cached payload is available ``NewsQuotaExceeded`` is raised
    when ``raise_on_quota_exhausted`` is true.
    """

    tkr = ticker.strip().upper()
    if not tkr:
        return []

    page = f"news_{tkr}"

    def _fetch_once() -> List[Dict[str, str]]:
        # Providers spend their own quota as they make requests; this only
        # refuses the fetch when none of them could make one.
        if not _can_request_news():
            raise NewsQuotaExceeded("news quota exceeded")
        return _fetch_news(tkr)

    def _call() -> List[Dict[str, str]]:
        return _single_flight(page, _fetch_once)

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
        return _tag_stale(cached if cached is not None else [], False)

    try:
        payload = _call()
    except NewsQuotaExceeded:
        if cached is not None:
            _warn_if_stale(page)
            stale = _is_cache_stale(page)
            _schedule_refresh()
            return _tag_stale(cached, stale)
        _schedule_refresh()
        if raise_on_quota_exhausted:
            raise
        return []

    payload = _trim_payload(payload)
    if not payload and cached is not None:
        # Use NEWS_TTL as the initial delay rather than an immediate retry:
        # with no delay the background loop's first call happens right away,
        # and since quota wasn't exhausted (we got this far) it would likely
        # fetch empty again and overwrite the still-good cached payload with
        # an empty one via save_cache.
        _warn_if_stale(page)
        _schedule_refresh(NEWS_TTL)
        return cached

    if cache_writer is not None:
        cache_writer(page, payload)
    else:
        page_cache.save_cache(page, payload)

    _schedule_refresh(NEWS_TTL)
    return _tag_stale(payload, False)


@router.get("/news")
def get_news(
    background_tasks: BackgroundTasks,
    ticker: str = Query(..., min_length=1),
) -> List[Dict[str, Any]]:
    """Return recent news headlines for ``ticker``."""

    tkr = ticker.strip().upper()
    if not tkr:
        return []
    try:
        return get_cached_news(
            tkr,
            cache_writer=lambda page, data: background_tasks.add_task(page_cache.save_cache, page, data),
            raise_on_quota_exhausted=True,
        )
    except NewsQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail="News request quota exceeded") from exc
