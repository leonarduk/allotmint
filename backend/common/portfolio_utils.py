"""
Common portfolio helpers

- list_all_unique_tickers()     -> returns all tickers in every portfolio
- get_security_meta(tkr)        -> basic metadata from portfolios
- aggregate_by_ticker(tree)     -> one row per ticker with latest-price snapshot
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd

from backend.common import portfolio as portfolio_mod
from backend.common.portfolio_loader import list_portfolios          # existing helper
from backend.common.instruments import get_instrument_meta
from backend.timeseries.cache import load_meta_timeseries_range
from backend.common.virtual_portfolio import (
    VirtualPortfolio,
    list_virtual_portfolios,
)

logger = logging.getLogger("portfolio_utils")


# ──────────────────────────────────────────────────────────────
# Risk helpers
# ──────────────────────────────────────────────────────────────
def compute_var(df: pd.DataFrame, confidence: float = 0.95) -> float | None:
    """Simple Value-at-Risk calculation from a price series.

    Returns the 1-day VaR for a notional single unit position based on the
    historical distribution of daily percentage returns. ``None`` is returned
    when the input ``DataFrame`` does not contain enough data.
    """

    if df is None or df.empty or "Close" not in df.columns:
        return None

    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(closes) < 2:
        return None

    returns = closes.pct_change().dropna()
    if returns.empty:
        return None

    var_pct = np.quantile(returns, 1 - confidence)
    last_price = float(closes.iloc[-1])
    var = -var_pct * last_price
    return float(var)

# ──────────────────────────────────────────────────────────────
# Numeric helper
# ──────────────────────────────────────────────────────────────
def _safe_num(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────
# Snapshot loader (last_price / deltas)
# ──────────────────────────────────────────────────────────────
_PRICES_PATH = Path("data/prices/latest_prices.json")

def _load_snapshot() -> Dict[str, Dict]:
    if not _PRICES_PATH.exists():
        logger.warning("Price snapshot not found: %s", _PRICES_PATH)
        return {}
    try:
        return json.loads(_PRICES_PATH.read_text())
    except Exception as exc:
        logger.error("Failed to parse snapshot %s: %s", _PRICES_PATH, exc)
        return {}

_PRICE_SNAPSHOT: Dict[str, Dict] = _load_snapshot()


def refresh_snapshot_in_memory(new_snapshot: Dict[str, Dict] | None = None) -> None:
    """Call this from /prices/refresh when you write a new JSON snapshot."""
    global _PRICE_SNAPSHOT
    _PRICE_SNAPSHOT = new_snapshot or _load_snapshot()
    logger.debug("In-memory price snapshot refreshed, %d tickers", len(_PRICE_SNAPSHOT))


# ──────────────────────────────────────────────────────────────
# Securities universe
# ──────────────────────────────────────────────────────────────
INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"


def _currency_from_file(ticker: str) -> str | None:
    """Best-effort lookup of currency from data/instruments files."""
    sym, exch = (ticker.split(".", 1) + ["Unknown"])[:2]
    path = INSTRUMENTS_DIR / (exch or "Unknown") / f"{sym}.json"
    try:
        return json.loads(path.read_text()).get("currency")
    except Exception:
        return None


def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    portfolios = list_portfolios() + [vp.as_portfolio_dict() for vp in list_virtual_portfolios()]
    for pf in portfolios:
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name": h.get("name", tkr),
                    "exchange": h.get("exchange"),
                    "isin": h.get("isin"),
                    "currency": h.get("currency") or _currency_from_file(tkr),
                }
    return securities

_SECURITIES = _build_securities_from_portfolios()

def get_security_meta(ticker: str) -> Dict | None:
    """Return {'ticker', 'name', …} for *ticker*.

    Falls back to instrument files if the ticker isn't present in portfolios.
    """
    t = ticker.upper()
    meta = _SECURITIES.get(t)
    if meta:
        return meta
    ccy = _currency_from_file(t)
    if ccy:
        return {"ticker": t, "name": t, "currency": ccy}
    return None


# ----------------------------------------------------------------------
# list_all_unique_tickers
# ----------------------------------------------------------------------
ACCOUNTS_DIR = Path(__file__).resolve().parents[2] / "data" / "accounts"

def list_all_unique_tickers() -> List[str]:
    portfolios = list_portfolios() + [vp.as_portfolio_dict() for vp in list_virtual_portfolios()]
    tickers: set[str] = set()
    total_accounts = 0
    total_holdings = 0
    null_ticker_count = 0

    for pf_idx, pf in enumerate(portfolios):
        accounts = pf.get("accounts", [])
        total_accounts += len(accounts)
        logger.debug("Portfolio %d has %d accounts", pf_idx + 1, len(accounts))

        for acct_idx, acct in enumerate(accounts):
            owner = pf.get("owner", f"pf{pf_idx+1}")
            account_type = acct.get("account_type", "unknown").lower()
            json_path = ACCOUNTS_DIR / owner / f"{account_type}.json"

            holdings = acct.get("holdings", [])
            total_holdings += len(holdings)

            for h_idx, h in enumerate(holdings):
                ticker = h.get("ticker")
                if ticker:
                    tickers.add(ticker.upper())
                else:
                    null_ticker_count += 1
                    logger.warning(
                        "Missing ticker in holding %d of %s -> %s",
                        h_idx + 1,
                        account_type,
                        json_path,
                    )

    logger.info(
        "list_all_unique_tickers: %d portfolios, %d accounts, %d holdings, "
        "%d unique tickers, %d null tickers",
        len(portfolios), total_accounts, total_holdings,
        len(tickers), null_ticker_count,
    )
    return sorted(tickers)


# ──────────────────────────────────────────────────────────────
# Core aggregation
# ──────────────────────────────────────────────────────────────
def aggregate_by_ticker(portfolio: dict | VirtualPortfolio) -> List[dict]:
    """
    Collapse a nested portfolio tree into one row per ticker,
    enriched with latest-price snapshot.
    """
    if isinstance(portfolio, VirtualPortfolio):
        portfolio = portfolio.as_portfolio_dict()
    rows: Dict[str, dict] = {}

    for account in portfolio.get("accounts", []):
        for h in account.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            meta = get_instrument_meta(tkr)

            row = rows.setdefault(
                tkr,
                {
                    "ticker":           tkr,
                    "name":             meta.get("name") or h.get("name", tkr),
                    "currency":         h.get("currency"),
                    "units":            0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp":         0.0,
                    "cost_gbp":         0.0,
                    "last_price_gbp":   None,
                    "last_price_date":  None,
                    "change_7d_pct":    None,
                    "change_30d_pct":   None,
                    "currency":        meta.get("currency"),
                    "instrument_type": meta.get("instrumentType") or meta.get("instrument_type"),
                },
            )

            # accumulate units & cost
            # accumulate units & cost (allow for differing field names)
            row["units"] += _safe_num(h.get("units"))

            if row.get("currency") is None:
                meta = get_security_meta(tkr)
                if meta and meta.get("currency"):
                    row["currency"] = meta["currency"]

            # attach snapshot if present
            cost = _safe_num(
                h.get("cost_gbp")
                or h.get("cost_basis_gbp")
                or h.get("effective_cost_basis_gbp")
            )
            row["cost_gbp"] += cost

            # if holdings already carry market value / gain, include them so we
            # have sensible numbers even when no price snapshot is available
            row["market_value_gbp"] += _safe_num(h.get("market_value_gbp"))
            row["gain_gbp"] += _safe_num(h.get("gain_gbp"))

            # attach snapshot if present – overrides derived values above
            snap = _PRICE_SNAPSHOT.get(tkr)
            price = snap.get("last_price") if isinstance(snap, dict) else None
            if price and price == price:  # guard against None/NaN/0
                row["last_price_gbp"] = price
                row["last_price_date"] = snap.get("last_price_date")
                row["change_7d_pct"] = snap.get("change_7d_pct")
                row["change_30d_pct"] = snap.get("change_30d_pct")
                row["market_value_gbp"] = round(row["units"] * price, 2)
                row["gain_gbp"] = (
                    round(row["market_value_gbp"] - row["cost_gbp"], 2)
                    if row["cost_gbp"] else row["gain_gbp"]
                )

            # pass-through misc attributes (first non-null wins)
            for k in ("asset_class", "region", "owner"):
                if k not in row and h.get(k) is not None:
                    row[k] = h[k]

    for r in rows.values():
        cost = r["cost_gbp"]
        r["gain_pct"] = (r["gain_gbp"] / cost * 100.0) if cost else None

    return list(rows.values())


# ──────────────────────────────────────────────────────────────
# Performance helpers
# ──────────────────────────────────────────────────────────────
def compute_owner_performance(owner: str, days: int = 365) -> Dict[str, Any]:
    """Return daily portfolio values and returns for an ``owner``.

    The calculation uses current holdings and fetches closing prices from the
    meta timeseries cache for the requested rolling window. The result is
    returned as ``{"history": [...], "max_drawdown": float}`` where
    ``history`` is a list of records::

        {
            "date": "2024-01-01",
            "value": 1234.56,
            "daily_return": 0.0012,         # 0.12 %
            "weekly_return": 0.0345,        # 3.45 %
            "cumulative_return": 0.0567,    # 5.67 % from start
            "running_max": 1500.0,          # peak value so far
            "drawdown": -0.18,              # % drop from running max
        }

    Returns ``{"history": [], "max_drawdown": None}`` if the owner or
    timeseries data is missing.
    """

    try:
        pf = portfolio_mod.build_owner_portfolio(owner)
    except FileNotFoundError:
        raise

    holdings: List[tuple[str, str, float]] = []  # (ticker, exchange, units)
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            units = _safe_num(h.get("units"))
            if not units:
                continue
            exch = (h.get("exchange") or "L").upper()
            holdings.append((tkr.split(".", 1)[0], exch, units))

    if not holdings:
        return {"history": [], "max_drawdown": None}

    total = pd.Series(dtype=float)
    for ticker, exchange, units in holdings:
        df = load_meta_timeseries(ticker, exchange, days)
        if df.empty or "Date" not in df.columns or "Close" not in df.columns:
            continue
        df = df[["Date", "Close"]].copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        values = df.set_index("Date")["Close"] * units
        total = total.add(values, fill_value=0)

    if total.empty:
        return {"history": [], "max_drawdown": None}

    perf = total.sort_index().to_frame(name="value")
    perf["daily_return"] = perf["value"].pct_change()
    perf["weekly_return"] = perf["value"].pct_change(5)
    start_val = perf["value"].iloc[0]
    perf["cumulative_return"] = perf["value"] / start_val - 1
    perf["running_max"] = perf["value"].cummax()
    perf["drawdown"] = perf["value"] / perf["running_max"] - 1
    max_drawdown = float(perf["drawdown"].min())
    perf = perf.reset_index().rename(columns={"index": "date"})

    out: List[Dict] = []
    for row in perf.itertuples(index=False):
        out.append(
            {
                "date": row.Date.isoformat(),
                "value": round(float(row.value), 2),
                "daily_return": (
                    float(row.daily_return) if pd.notna(row.daily_return) else None
                ),
                "weekly_return": (
                    float(row.weekly_return) if pd.notna(row.weekly_return) else None
                ),
                "cumulative_return": (
                    float(row.cumulative_return)
                    if pd.notna(row.cumulative_return)
                    else None
                ),
                "running_max": round(float(row.running_max), 2),
                "drawdown": (
                    float(row.drawdown) if pd.notna(row.drawdown) else None
                ),
            }
        )

    return {"history": out, "max_drawdown": max_drawdown}


# ──────────────────────────────────────────────────────────────
# Snapshot refresher (used by /prices/refresh)
# ──────────────────────────────────────────────────────────────
def refresh_snapshot_in_memory_from_timeseries(days: int = 365) -> None:
    """
    Pull a closing-price snapshot from the meta timeseries cache
    and write it to *data/prices/latest_prices.json* in the canonical
    shape used by the rest of the backend.
    """
    from backend.timeseries.cache import fetch_meta_timeseries

    tickers = list_all_unique_tickers()
    snapshot: Dict[str, Dict[str, str | float]] = {}

    for t in tickers:
        try:
            today = datetime.today().date()
            cutoff = today - timedelta(days=days)
            ticker_only, exchange = (t.split(".", 1) + ["L"])[:2]

            df = load_meta_timeseries_range(ticker=ticker_only, exchange=exchange,
                                        start_date=cutoff, end_date=today)

            if df is not None and not df.empty:
                # Map lowercase column names to their actual counterparts
                name_map = {c.lower(): c for c in df.columns}

                # Access the close column in a case-insensitive manner
                if "close" in name_map:
                    latest_row = df.iloc[-1]
                    close_col = name_map["close"]
                    snapshot[t] = {
                        "last_price": float(latest_row[close_col]),
                        "last_price_date": latest_row["Date"].strftime("%Y-%m-%d"),
                    }
        except Exception as e:
            logger.warning("Could not get timeseries for %s: %s", t, e)

    # store in-memory
    _PRICE_SNAPSHOT.clear()
    _PRICE_SNAPSHOT.update(snapshot)

    # write to disk
    try:
        _PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PRICES_PATH.write_text(json.dumps(snapshot, indent=2))
        logger.info("Wrote %d prices to %s", len(snapshot), _PRICES_PATH)
    except Exception as e:
        logger.warning("Failed to write latest_prices.json: %s", e)

    logger.info("Refreshed %d price entries", len(snapshot))

# ──────────────────────────────────────────────────────────────
# Alert helpers
# ──────────────────────────────────────────────────────────────
def check_price_alerts(threshold_pct: float = 0.1) -> List[Dict]:
    """Check holdings against cost basis and emit alerts."""
    from backend.common.alerts import publish_sns_alert

    alerts: List[Dict] = []
    for pf in list_portfolios():
        for row in aggregate_by_ticker(pf):
            cost = _safe_num(row.get("cost_gbp"))
            mv = _safe_num(row.get("market_value_gbp"))
            if cost <= 0 or mv <= 0:
                continue
            change_pct = (mv - cost) / cost
            if abs(change_pct) >= threshold_pct:
                alert = {
                    "ticker": row["ticker"],
                    "change_pct": round(change_pct, 4),
                    "message": f"{row['ticker']} change {change_pct*100:.1f}% vs cost basis",
                }
                publish_sns_alert(alert)
                alerts.append(alert)
    return alerts
