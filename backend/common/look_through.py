"""Real (look-through) exposure by country, sector and holding (#9974).

Combines directly held shares with the published breakdown of each fund the
portfolio holds (the ``look_through`` block in instrument metadata, written by
``scripts/refresh_look_through.py``):

* a directly held share counts 100% to its own sector, country (``country``
  metadata, else its ISIN prefix) and holding;
* a fund with look-through data is split by its country/sector weights, and
  its published top holdings are matched to direct holdings by ISIN, so a
  stock owned directly and inside several funds shows as one exposure;
* the part of a fund outside its published top holdings is reported as one
  "Other holdings in funds" line, and a fund without look-through data keeps
  its own sector with country "Not looked through" -- nothing is dropped, so
  every breakdown sums to the portfolio value.

This only reads stored metadata; it never fetches from a data source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from backend.common.country_codes import country_from_isin, country_name
from backend.common.instrument_classification import COMMODITY, derive_asset_class, exposure_sector, is_fund
from backend.common.instruments import get_instrument_meta, save_instrument_meta
from backend.common.look_through_sources import fetch_look_through, source_page_url
from backend.common.portfolio_utils import aggregate_by_ticker
from backend.common.sector_labels import (
    CASH_SECTOR_LABEL,
    is_cash_instrument,
    normalise_optional_region,
    normalise_optional_sector,
)

UNKNOWN_LABEL = "Unknown"
NOT_LOOKED_THROUGH = "Not looked through"
COMMODITIES_COUNTRY = "Commodities"
OTHER_FUND_HOLDINGS_KEY = "OTHER-IN-FUNDS"
OTHER_FUND_HOLDINGS_NAME = "Other holdings in funds"
DEFAULT_HOLDINGS_LIMIT = 50
# Look-through blocks fetched within this many days are not refetched: neither
# source is an official API, so refreshes are kept to roughly monthly.
DEFAULT_MAX_AGE_DAYS = 25


def look_through_is_fresh(meta: Dict[str, Any], today: date, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
    """True when ``meta``'s ``look_through`` block was fetched within ``max_age_days`` of ``today``."""
    block = meta.get("look_through")
    fetched = block.get("fetched") if isinstance(block, dict) else None
    try:
        return bool(fetched) and date.fromisoformat(str(fetched)) >= today - timedelta(days=max_age_days)
    except ValueError:
        return False


@dataclass
class _Holding:
    key: str
    name: str
    isin: Optional[str]
    kind: str
    direct_value_gbp: float = 0.0
    via_funds_value_gbp: float = 0.0
    sources: Dict[str, float] = field(default_factory=dict)

    @property
    def value_gbp(self) -> float:
        return self.direct_value_gbp + self.via_funds_value_gbp


@dataclass
class _Exposure:
    countries: Dict[str, float] = field(default_factory=dict)
    sectors: Dict[str, float] = field(default_factory=dict)
    holdings: Dict[str, _Holding] = field(default_factory=dict)
    funds: List[Dict[str, Any]] = field(default_factory=list)
    not_covered: List[Dict[str, Any]] = field(default_factory=list)
    direct_value_gbp: float = 0.0
    cash_value_gbp: float = 0.0

    def add_country(self, label: str, value: float) -> None:
        self.countries[label] = self.countries.get(label, 0.0) + value

    def add_sector(self, label: str, value: float) -> None:
        self.sectors[label] = self.sectors.get(label, 0.0) + value

    def holding(self, key: str, name: str, isin: Optional[str], kind: str) -> _Holding:
        existing = self.holdings.get(key)
        if existing is None:
            existing = self.holdings[key] = _Holding(key=key, name=name, isin=isin, kind=kind)
        return existing


def _clean_isin(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    isin = value.strip().upper()
    return isin if len(isin) == 12 and isin[:2].isalpha() else None


def _country_label(value: Any) -> Optional[str]:
    """Display country for a ``country``/``region`` value, expanding ISO codes such as ``US``."""
    label = normalise_optional_region(value)
    if label and len(label) <= 3 and label.isalpha():
        return country_name(label)
    return label


def _security_country(meta: Dict[str, Any], region: Any = None) -> str:
    """Country of a directly held share: ``country`` metadata, ISIN prefix, then region code."""
    return (
        _country_label(meta.get("country"))
        or country_from_isin(_clean_isin(meta.get("isin")))
        or _country_label(region if region is not None else meta.get("region"))
        or UNKNOWN_LABEL
    )


def _weights(block: Dict[str, Any], key: str) -> Dict[str, float]:
    """``{label: share}`` from a look-through weight map, rescaled to sum to 1."""
    raw = block.get(key)
    if not isinstance(raw, dict):
        return {}
    weights = {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float)) and v > 0}
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {}


def usable_look_through(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The metadata's ``look_through`` block if it carries country and sector weights."""
    block = meta.get("look_through")
    if not isinstance(block, dict):
        return None
    if not _weights(block, "countries") or not _weights(block, "sectors"):
        return None
    return block


def _add_fund_holdings(exp: _Exposure, ticker: str, value: float, block: Dict[str, Any]) -> None:
    covered = 0.0
    for h in block.get("top_holdings") or []:
        weight = h.get("weight_pct") if isinstance(h, dict) else None
        name = h.get("name") if isinstance(h, dict) else None
        if not isinstance(weight, (int, float)) or weight <= 0 or not name:
            continue
        weight = min(float(weight), 100.0 - covered)
        if weight <= 0:
            break
        covered += weight
        isin = _clean_isin(h.get("isin"))
        held = exp.holding(isin or f"NAME:{str(name).strip().upper()}", str(name).strip(), isin, "security")
        part = value * weight / 100.0
        held.via_funds_value_gbp += part
        held.sources[ticker] = held.sources.get(ticker, 0.0) + part
    residual = value * (100.0 - covered) / 100.0
    if residual > 0:
        other = exp.holding(OTHER_FUND_HOLDINGS_KEY, OTHER_FUND_HOLDINGS_NAME, None, "other")
        other.via_funds_value_gbp += residual
        other.sources[ticker] = other.sources.get(ticker, 0.0) + residual


def _add_fund(exp: _Exposure, row: Dict[str, Any], value: float, block: Dict[str, Any]) -> None:
    ticker = row["ticker"]
    for label, share in _weights(block, "countries").items():
        exp.add_country(label, value * share)
    for label, share in _weights(block, "sectors").items():
        exp.add_sector(label, value * share)
    if block.get("top_holdings"):
        _add_fund_holdings(exp, ticker, value, block)
    else:
        # A hand-entered block (country/sector only) lists no holdings: the
        # fund itself stays one line rather than vanishing into "Other".
        isin = _clean_isin((get_instrument_meta(ticker) or {}).get("isin"))
        held = exp.holding(isin or ticker, str(row.get("name") or ticker), isin, "fund")
        held.direct_value_gbp += value
        held.sources[ticker] = held.sources.get(ticker, 0.0) + value
    exp.funds.append(
        {
            "ticker": ticker,
            "name": row.get("name") or ticker,
            "value_gbp": round(value, 2),
            "source": block.get("source"),
            "as_of": block.get("as_of"),
            "holdings_count": block.get("holdings_count"),
        }
    )


def _add_direct(exp: _Exposure, row: Dict[str, Any], value: float, meta: Dict[str, Any], fund: bool) -> None:
    ticker = row["ticker"]
    isin = _clean_isin(meta.get("isin"))
    sector = normalise_optional_sector(row.get("sector")) or UNKNOWN_LABEL
    if fund:
        # A commodity ETC has no country to look through to; any other fund just lacks data.
        country = COMMODITIES_COUNTRY if derive_asset_class(meta) == COMMODITY else NOT_LOOKED_THROUGH
        exp.not_covered.append({"ticker": ticker, "name": row.get("name") or ticker, "value_gbp": round(value, 2)})
    else:
        country = _security_country(meta, row.get("region"))
        exp.direct_value_gbp += value
    exp.add_country(country, value)
    exp.add_sector(sector, value)
    held = exp.holding(isin or ticker, str(row.get("name") or ticker), isin, "fund" if fund else "security")
    held.name = str(row.get("name") or held.name)
    held.direct_value_gbp += value
    held.sources[ticker] = held.sources.get(ticker, 0.0) + value


def _add_row(exp: _Exposure, row: Dict[str, Any]) -> None:
    value = float(row.get("market_value_gbp") or 0.0)
    ticker = row.get("ticker")
    if not value or not ticker:
        return
    if is_cash_instrument(ticker, row.get("instrument_type")):
        exp.cash_value_gbp += value
        exp.add_country(CASH_SECTOR_LABEL, value)
        exp.add_sector(CASH_SECTOR_LABEL, value)
        cash = exp.holding("CASH", CASH_SECTOR_LABEL, None, "cash")
        cash.direct_value_gbp += value
        cash.sources[ticker] = cash.sources.get(ticker, 0.0) + value
        return
    meta = get_instrument_meta(ticker) or {}
    block = usable_look_through(meta)
    if block is not None:
        _add_fund(exp, row, value, block)
    else:
        fund = is_fund({**meta, "instrumentType": meta.get("instrumentType") or row.get("instrument_type")})
        _add_direct(exp, row, value, meta, fund)


def _buckets(weights: Dict[str, float], total: float) -> List[Dict[str, Any]]:
    rows = [
        {"label": label, "value_gbp": round(value, 2), "weight_pct": round(value / total * 100.0, 4) if total else 0.0}
        for label, value in weights.items()
    ]
    return sorted(rows, key=lambda r: r["value_gbp"], reverse=True)


def _holding_rows(exp: _Exposure, total: float, limit: int) -> List[Dict[str, Any]]:
    ranked = sorted(exp.holdings.values(), key=lambda h: h.value_gbp, reverse=True)
    other = exp.holdings.get(OTHER_FUND_HOLDINGS_KEY)
    shown = [h for h in ranked if h.key != OTHER_FUND_HOLDINGS_KEY][:limit]
    if other is not None and limit > 0:
        shown.append(other)
    return [
        {
            "key": h.key,
            "name": h.name,
            "isin": h.isin,
            "kind": h.kind,
            "value_gbp": round(h.value_gbp, 2),
            "weight_pct": round(h.value_gbp / total * 100.0, 4) if total else 0.0,
            "direct_value_gbp": round(h.direct_value_gbp, 2),
            "via_funds_value_gbp": round(h.via_funds_value_gbp, 2),
            "sources": [
                {"ticker": t, "value_gbp": round(v, 2)} for t, v in sorted(h.sources.items(), key=lambda kv: -kv[1])
            ],
        }
        for h in shown
    ]


def compute_look_through(portfolio: Dict[str, Any], holdings_limit: int = DEFAULT_HOLDINGS_LIMIT) -> Dict[str, Any]:
    """Look-through exposure of ``portfolio`` (an owner or group portfolio dict)."""
    exp = _Exposure()
    for row in aggregate_by_ticker(portfolio):
        _add_row(exp, row)
    total = sum(exp.countries.values())
    funds_value = sum(f["value_gbp"] for f in exp.funds)
    not_covered_value = sum(f["value_gbp"] for f in exp.not_covered)
    return {
        "total_value_gbp": round(total, 2),
        "countries": _buckets(exp.countries, total),
        "sectors": _buckets(exp.sectors, total),
        "holdings": _holding_rows(exp, total, max(holdings_limit, 0)),
        "coverage": {
            "looked_through_value_gbp": round(funds_value, 2),
            "direct_value_gbp": round(exp.direct_value_gbp, 2),
            "not_covered_value_gbp": round(not_covered_value, 2),
            "cash_value_gbp": round(exp.cash_value_gbp, 2),
            "funds": sorted(exp.funds, key=lambda f: -f["value_gbp"]),
            "not_covered": sorted(exp.not_covered, key=lambda f: -f["value_gbp"]),
        },
    }


def _pct_rows(weights: Dict[str, float]) -> List[Dict[str, Any]]:
    rows = [{"label": label, "weight_pct": round(share * 100.0, 4)} for label, share in weights.items()]
    return sorted(rows, key=lambda r: r["weight_pct"], reverse=True)


def _fund_allocation(base: Dict[str, Any], block: Dict[str, Any], isin: Any) -> Dict[str, Any]:
    return {
        **base,
        "kind": "fund",
        "source": block.get("source"),
        # A manual block (from a fund's own report) records its document URL.
        "source_url": block.get("source_url") or source_page_url(block.get("source"), isin),
        "as_of": block.get("as_of"),
        "fetched": block.get("fetched"),
        "note": block.get("note"),
        "holdings_count": block.get("holdings_count"),
        "asset_mix": block.get("asset_mix"),
        "countries": _pct_rows(_weights(block, "countries")),
        "sectors": _pct_rows(_weights(block, "sectors")),
        "top_holdings": [h for h in block.get("top_holdings") or [] if isinstance(h, dict)],
    }


def instrument_allocation(ticker: str) -> Dict[str, Any]:
    """Country/sector/holding breakdown of one instrument for its Research page (#9974).

    ``kind`` is ``"fund"`` (stored look-through data), ``"security"`` (a single
    share: 100% its own country, sector and holding), ``"fund_uncovered"`` (a
    fund with no look-through data yet) or ``"cash"``.
    """
    meta = get_instrument_meta(ticker) or {}
    name = str(meta.get("name") or ticker)
    sector = normalise_optional_sector(exposure_sector(meta) or meta.get("sector")) or UNKNOWN_LABEL
    base: Dict[str, Any] = {
        "ticker": ticker,
        "name": name,
        "source": None,
        "source_url": None,
        "as_of": None,
        "fetched": None,
        "note": None,
        "holdings_count": None,
    }
    if is_cash_instrument(ticker, meta.get("instrumentType")):
        cash = [{"label": CASH_SECTOR_LABEL, "weight_pct": 100.0}]
        return {**base, "kind": "cash", "asset_mix": None, "countries": cash, "sectors": cash, "top_holdings": []}
    block = usable_look_through(meta)
    if block is not None:
        return _fund_allocation(base, block, meta.get("isin"))
    if is_fund(meta):
        country = COMMODITIES_COUNTRY if derive_asset_class(meta) == COMMODITY else NOT_LOOKED_THROUGH
        return {
            **base,
            "kind": "fund_uncovered",
            "asset_mix": None,
            "countries": [{"label": country, "weight_pct": 100.0}],
            "sectors": [{"label": sector, "weight_pct": 100.0}],
            "top_holdings": [],
        }
    country = _security_country(meta)
    holding = {
        "name": name,
        "isin": _clean_isin(meta.get("isin")),
        "weight_pct": 100.0,
        "country": country,
        "sector": sector,
    }
    return {
        **base,
        "kind": "security",
        "asset_mix": None,
        "countries": [{"label": country, "weight_pct": 100.0}],
        "sectors": [{"label": sector, "weight_pct": 100.0}],
        "top_holdings": [holding],
    }


class LookThroughRefreshError(ValueError):
    """The instrument cannot be refreshed (unknown, or no ISIN to look it up by)."""


def refresh_instrument_look_through(ticker: str) -> Dict[str, Any]:
    """Fetch ``ticker``'s look-through data now (Morningstar, then justETF) and store it (#9974).

    Returns ``{"updated": bool, "allocation": ...}``; ``updated`` is false when
    no source covers the fund, leaving any stored block untouched. Network and
    source errors propagate (``requests.RequestException`` /
    ``LookThroughFetchError``) for the caller to report.
    """
    meta = get_instrument_meta(ticker)
    if not meta:
        raise LookThroughRefreshError(f"No metadata for {ticker}")
    isin = _clean_isin(meta.get("isin"))
    if not isin:
        raise LookThroughRefreshError(f"{ticker} has no ISIN to look up")
    block = fetch_look_through(isin)
    if block is not None:
        save_instrument_meta(ticker, {**meta, "look_through": block}, sort_keys=False)
    return {"updated": block is not None, "allocation": instrument_allocation(ticker)}
