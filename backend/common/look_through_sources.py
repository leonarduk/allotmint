"""Fetch a fund's country/sector/top-holding breakdown for look-through (#9974).

Two sources, tried in order by :func:`fetch_look_through`:

* **Morningstar** -- the ``lt.morningstar.com`` screener resolves an ISIN to a
  SecId, and the ``ITsnapshot`` view of ``security_details`` carries the latest
  portfolio: asset mix, country exposure per sleeve, Morningstar global sector
  breakdown and the top holdings (with ISIN, country and sector). Covers ETFs,
  investment trusts and OEICs.
* **justETF** -- the ETF profile page lists the top countries/sectors (plus an
  "Other" remainder) and top 10 holdings. UCITS ETFs only.

Neither is an official API and both sites restrict automated access, so this
module is only called from the explicit refresh script
(``scripts/refresh_look_through.py``); a page read never fetches. Results are
normalised into the ``look_through`` block stored in instrument metadata, with
``sectors`` and ``countries`` expressed as % of the whole fund.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from backend.common.country_codes import country_name
from backend.common.sector_labels import CASH_SECTOR_LABEL, normalise_sector_label

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
REQUEST_TIMEOUT_S = 30
MAX_TOP_HOLDINGS = 25

FIXED_INCOME_LABEL = "Fixed Income"
OTHER_LABEL = "Other"
UNCLASSIFIED_COUNTRY = "Unclassified"

MORNINGSTAR_BASE = "https://lt.morningstar.com/api/rest.svc/klr5zyak8x"
MORNINGSTAR_UNIVERSES = "FOGBR$$ALL|ETEUR$$ALL|FCGBR$$ALL|CEEXG$XLON|FCEUR$$ALL|E0WWE$$ALL"
# Morningstar "MorningStarDefault" asset-allocation types -> sleeve.
_MS_ASSET_TYPES = {"1": "equity", "3": "bond", "6": "bond", "7": "cash"}
# Morningstar global equity sector ids; names are folded into GICS labels.
_MS_SECTORS = {
    "101": "Basic Materials",
    "102": "Consumer Cyclical",
    "103": "Financial Services",
    "104": "Real Estate",
    "205": "Consumer Defensive",
    "206": "Healthcare",
    "207": "Utilities",
    "308": "Communication Services",
    "309": "Energy",
    "310": "Industrials",
    "311": "Technology",
}

JUSTETF_PROFILE_URL = "https://www.justetf.com/en/etf-profile.html"
_JUSTETF_SECTORS = {
    "Finance": "Financials",
    "Consumer Non-Cyclicals": "Consumer Staples",
    "Consumer Cyclicals": "Consumer Discretionary",
    "Telecommunication": "Communication Services",
}
_PCT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_JUSTETF_AS_OF_RE = re.compile(r"As of (\d{2})/(\d{2})/(\d{4})")


def source_page_url(source: object, isin: object) -> Optional[str]:
    """A public page for the fund on ``source`` (by ISIN), for showing where the data came from."""
    if not isinstance(isin, str) or not isin.strip():
        return None
    query = requests.utils.quote(isin.strip().upper())
    if source == "morningstar":
        return f"https://global.morningstar.com/en-gb/search?query={query}"
    if source == "justetf":
        return f"{JUSTETF_PROFILE_URL}?isin={query}"
    return None


class LookThroughFetchError(RuntimeError):
    """A source answered, but not with usable data (HTTP error, bad payload)."""


def new_session() -> requests.Session:
    """A session with browser-like headers; justETF rejects the default ``python-requests`` agent."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html"})
    return s


def _session(session: Optional[requests.Session]) -> requests.Session:
    return session if session is not None else new_session()


def _get(session: requests.Session, url: str, params: Dict[str, Any]) -> requests.Response:
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
    if resp.status_code != 200:
        raise LookThroughFetchError(f"{url} returned HTTP {resp.status_code}")
    return resp


def _round_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Drop zero buckets, round to 4 dp and sort largest first."""
    kept = {k: round(v, 4) for k, v in weights.items() if abs(v) >= 0.00005}
    return dict(sorted(kept.items(), key=lambda kv: kv[1], reverse=True))


def _add(weights: Dict[str, float], key: str, value: float) -> None:
    weights[key] = weights.get(key, 0.0) + value


# ──────────────────────────────────────────────────────────────
# Morningstar
# ──────────────────────────────────────────────────────────────
def morningstar_sec_ids(isin: str, session: Optional[requests.Session] = None) -> List[str]:
    """Morningstar SecIds listed under ``isin`` (one per share class/listing), best first."""
    params = {
        "page": 1,
        "pageSize": 10,
        "outputType": "json",
        "version": 1,
        "languageId": "en-GB",
        "currencyId": "GBP",
        "universeIds": MORNINGSTAR_UNIVERSES,
        "securityDataPoints": "SecId|Name|isin|Universe",
        "term": isin,
    }
    try:
        rows = _get(_session(session), f"{MORNINGSTAR_BASE}/security/screener", params).json().get("rows") or []
    except ValueError as exc:
        raise LookThroughFetchError(f"Morningstar search for {isin} returned invalid JSON") from exc
    return [str(r["SecId"]) for r in rows if r.get("SecId") and str(r.get("isin") or "").upper() == isin.upper()]


def morningstar_snapshot(sec_id: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Raw ``ITsnapshot`` security details for ``sec_id``."""
    params = {
        "viewId": "ITsnapshot",
        "idtype": "msid",
        "responseViewFormat": "json",
        "currencyId": "GBP",
        "languageId": "en-GB",
    }
    try:
        data = _get(_session(session), f"{MORNINGSTAR_BASE}/security_details/{sec_id}", params).json()
    except ValueError as exc:
        raise LookThroughFetchError(f"Morningstar snapshot for {sec_id} returned invalid JSON") from exc
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise LookThroughFetchError(f"Morningstar snapshot for {sec_id} is not an object")
    return data


def _net_breakdowns(portfolio: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    """The net (``SalePosition == "N"``) entries of breakdown ``key``."""
    return [b for b in portfolio.get(key) or [] if isinstance(b, dict) and b.get("SalePosition") == "N"]


def _ms_asset_mix(portfolio: Dict[str, Any]) -> Dict[str, float]:
    """Sleeve weights (% of fund) with shorts/leverage clipped and rescaled to 100."""
    entries = [e for e in _net_breakdowns(portfolio, "AssetAllocations") if e.get("Type") == "MorningStarDefault"]
    mix: Dict[str, float] = {}
    for item in (entries[0].get("BreakdownValues") or []) if entries else []:
        value = float(item.get("Value") or 0.0)
        if value > 0:
            _add(mix, _MS_ASSET_TYPES.get(str(item.get("Type")), "other"), value)
    total = sum(mix.values())
    if total <= 0:
        return {}
    return {k: v * 100.0 / total for k, v in mix.items()}


def _breakdown_shares(entry: Dict[str, Any]) -> Dict[str, float]:
    """``{type: share of the classified part}`` (shares sum to 1) for one breakdown entry."""
    values = {str(b.get("Type")): float(b.get("Value") or 0.0) for b in entry.get("BreakdownValues") or []}
    values = {k: v for k, v in values.items() if v > 0}
    total = sum(values.values())
    return {k: v / total for k, v in values.items()} if total > 0 else {}


def _ms_countries(portfolio: Dict[str, Any], mix: Dict[str, float]) -> Dict[str, float]:
    by_sleeve = {
        str(e.get("Type") or "").lower(): _breakdown_shares(e) for e in _net_breakdowns(portfolio, "CountryExposure")
    }
    countries: Dict[str, float] = {}
    for sleeve, weight in mix.items():
        shares = by_sleeve.get(sleeve) or {}
        if sleeve == "cash":
            _add(countries, CASH_SECTOR_LABEL, weight)
        elif not shares:
            _add(countries, UNCLASSIFIED_COUNTRY if sleeve != "other" else OTHER_LABEL, weight)
        for code, share in shares.items():
            _add(countries, country_name(code) or UNCLASSIFIED_COUNTRY, weight * share)
    return _round_weights(countries)


def _ms_sectors(portfolio: Dict[str, Any], mix: Dict[str, float]) -> Dict[str, float]:
    entries = _net_breakdowns(portfolio, "GlobalStockSectorBreakdown")
    equity_shares = _breakdown_shares(entries[0]) if entries else {}
    sectors: Dict[str, float] = {}
    for sleeve, weight in mix.items():
        if sleeve == "equity" and equity_shares:
            for code, share in equity_shares.items():
                label = normalise_sector_label(_MS_SECTORS.get(code, OTHER_LABEL))
                _add(sectors, label, weight * share)
        else:
            label = {"bond": FIXED_INCOME_LABEL, "cash": CASH_SECTOR_LABEL}.get(sleeve, OTHER_LABEL)
            _add(sectors, label, weight)
    return _round_weights(sectors)


def _ms_holdings(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    holdings = []
    for h in portfolio.get("PortfolioHoldings") or []:
        weight = h.get("Weighting")
        name = h.get("SecurityName") or h.get("ExternalName")
        if not name or not isinstance(weight, (int, float)) or weight <= 0:
            continue
        sector_id = str(h.get("GlobalSectorId") or "")
        holdings.append(
            {
                "name": str(name).strip(),
                "isin": (h.get("ISIN") or None),
                "weight_pct": round(float(weight), 4),
                "country": country_name(h.get("CountryId")),
                "sector": normalise_sector_label(_MS_SECTORS[sector_id]) if sector_id in _MS_SECTORS else None,
            }
        )
    holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
    return holdings[:MAX_TOP_HOLDINGS]


def _ms_holdings_count(portfolio: Dict[str, Any]) -> Optional[int]:
    for agg in portfolio.get("HoldingAggregates") or []:
        if agg.get("SalePosition") == "N" and not agg.get("HoldingsType") and agg.get("NumberOfHolding"):
            return int(agg["NumberOfHolding"])
    return None


def _ms_pick_portfolio(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The snapshot portfolio carrying a country or sector breakdown, if any."""
    for p in snapshot.get("Portfolios") or []:
        if isinstance(p, dict) and (p.get("CountryExposure") or p.get("GlobalStockSectorBreakdown")):
            return p
    return None


def parse_morningstar_snapshot(snapshot: Dict[str, Any], sec_id: str, today: date) -> Optional[Dict[str, Any]]:
    """Normalise an ``ITsnapshot`` payload into a ``look_through`` block, or ``None`` if it has no breakdown."""
    portfolio = _ms_pick_portfolio(snapshot)
    if portfolio is None:
        return None
    mix = _ms_asset_mix(portfolio) or {"equity": 100.0}
    return {
        "source": "morningstar",
        "source_id": sec_id,
        "as_of": str(portfolio.get("Date") or "")[:10] or None,
        "fetched": today.isoformat(),
        "asset_mix": _round_weights(mix),
        "countries": _ms_countries(portfolio, mix),
        "sectors": _ms_sectors(portfolio, mix),
        "top_holdings": _ms_holdings(portfolio),
        "holdings_count": _ms_holdings_count(portfolio),
    }


def fetch_morningstar(
    isin: str, session: Optional[requests.Session] = None, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Look-through block for ``isin`` from Morningstar, or ``None`` if not covered."""
    s = _session(session)
    for sec_id in morningstar_sec_ids(isin, s)[:3]:
        block = parse_morningstar_snapshot(morningstar_snapshot(sec_id, s), sec_id, today or date.today())
        if block is not None:
            return block
    return None


# ──────────────────────────────────────────────────────────────
# justETF
# ──────────────────────────────────────────────────────────────
def _justetf_rows(soup: BeautifulSoup, test_id: str) -> List[tuple[str, float, Optional[str]]]:
    """``(label, pct, href)`` rows of the justETF holdings table tagged ``test_id``."""
    container = soup.find(attrs={"data-testid": test_id})
    rows: List[tuple[str, float, Optional[str]]] = []
    for tr in container.find_all("tr") if container else []:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        match = _PCT_RE.search(cells[-1]) if len(cells) >= 2 else None
        if not match or not cells[0]:
            continue
        link = tr.find("a")
        rows.append((cells[0], float(match.group(1)), link.get("href") if link else None))
    return rows


def _justetf_as_of(soup: BeautifulSoup) -> Optional[str]:
    match = _JUSTETF_AS_OF_RE.search(soup.get_text(" "))
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def parse_justetf_profile(html: str, isin: str, today: date) -> Optional[Dict[str, Any]]:
    """Normalise a justETF profile page into a ``look_through`` block, or ``None`` if it has no breakdown."""
    soup = BeautifulSoup(html, "lxml")
    countries = {label: pct for label, pct, _ in _justetf_rows(soup, "etf-holdings_countries_container")}
    sectors: Dict[str, float] = {}
    for label, pct, _ in _justetf_rows(soup, "etf-holdings_sectors_container"):
        _add(sectors, normalise_sector_label(_JUSTETF_SECTORS.get(label, label)), pct)
    if not countries and not sectors:
        return None
    holdings = []
    for label, pct, href in _justetf_rows(soup, "etf-holdings_top-holdings_container"):
        holding_isin = href.rstrip("/").rsplit("/", 1)[-1].upper() if href and "stock-profiles" in href else None
        holdings.append({"name": label, "isin": holding_isin, "weight_pct": pct, "country": None, "sector": None})
    return {
        "source": "justetf",
        "source_id": isin,
        "as_of": _justetf_as_of(soup),
        "fetched": today.isoformat(),
        "asset_mix": None,
        "countries": _round_weights(countries),
        "sectors": _round_weights(sectors),
        "top_holdings": holdings[:MAX_TOP_HOLDINGS],
        "holdings_count": None,
    }


def fetch_justetf(
    isin: str, session: Optional[requests.Session] = None, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Look-through block for ``isin`` from justETF, or ``None`` if not covered.

    justETF redirects an ISIN it does not list to its search page (which
    rejects scripted requests), so a redirect means "not covered".
    """
    resp = _session(session).get(
        JUSTETF_PROFILE_URL, params={"isin": isin}, timeout=REQUEST_TIMEOUT_S, allow_redirects=False
    )
    if resp.is_redirect:
        return None
    if resp.status_code != 200:
        raise LookThroughFetchError(f"{JUSTETF_PROFILE_URL} returned HTTP {resp.status_code}")
    return parse_justetf_profile(resp.text, isin, today or date.today())


def fetch_look_through(
    isin: str, session: Optional[requests.Session] = None, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Look-through block for ``isin``: Morningstar first, then justETF; ``None`` if neither covers it.

    A failure from one source is logged and the next source is tried; network
    errors from the last source propagate to the caller.
    """
    s = _session(session)
    try:
        block = fetch_morningstar(isin, s, today)
    except (requests.RequestException, LookThroughFetchError) as exc:
        logger.warning("Morningstar look-through failed for %s: %s; trying justETF", isin, exc)
        block = None
    if block is not None:
        return block
    return fetch_justetf(isin, s, today)
