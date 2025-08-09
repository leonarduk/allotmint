"""
Common portfolio helpers

• list_all_unique_tickers()     → returns all tickers in every portfolio
• get_security_meta(tkr)        → basic metadata from portfolios
• aggregate_by_ticker(tree)     → one row per ticker with latest-price snapshot
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Dict, List

from backend.common.portfolio_loader import list_portfolios          # existing helper
from backend.timeseries.cache import load_meta_timeseries

logger = logging.getLogger("portfolio_utils")

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
def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    for pf in list_portfolios():
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name":     h.get("name", tkr),
                    "exchange": h.get("exchange"),
                    "isin":     h.get("isin"),
                }
    return securities

_SECURITIES = _build_securities_from_portfolios()

def get_security_meta(ticker: str) -> Dict | None:
    """Return {'ticker', 'name', …} derived from current portfolios."""
    return _SECURITIES.get(ticker.upper())


# ----------------------------------------------------------------------
# list_all_unique_tickers
# ----------------------------------------------------------------------
ACCOUNTS_DIR = Path(__file__).resolve().parents[2] / "data" / "accounts"

def list_all_unique_tickers() -> List[str]:
    portfolios = list_portfolios()
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
                        "Missing ticker in holding %d of %s → %s",
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
def aggregate_by_ticker(portfolio: dict) -> List[dict]:
    """
    Collapse a nested portfolio tree into one row per ticker,
    enriched with latest-price snapshot.
    """
    rows: Dict[str, dict] = {}

    for account in portfolio.get("accounts", []):
        for h in account.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue

            row = rows.setdefault(
                tkr,
                {
                    "ticker":           tkr,
                    "name":             h.get("name", tkr),
                    "units":            0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp":         0.0,
                    "cost_gbp":         0.0,
                    "last_price_gbp":   None,
                    "last_price_date":  None,
                    "change_7d_pct":    None,
                    "change_30d_pct":   None,
                },
            )

            # accumulate units & cost
            row["units"] += _safe_num(h.get("units"))
            row["cost_gbp"] += _safe_num(h.get("cost_gbp"))

            # attach snapshot if present
            snap = _PRICE_SNAPSHOT.get(tkr)
            if isinstance(snap, dict):
                price = snap["last_price"]
                row["last_price_gbp"]  = price
                row["last_price_date"] = snap["last_price_date"]
                row["change_7d_pct"]   = snap.get("change_7d_pct")
                row["change_30d_pct"]  = snap.get("change_30d_pct")
                row["market_value_gbp"] = round(row["units"] * price, 2)
                row["gain_gbp"] = round(row["market_value_gbp"] - row["cost_gbp"], 2)

            # pass-through misc attributes (first non-null wins)
            for k in ("asset_class", "region", "owner"):
                if k not in row and h.get(k) is not None:
                    row[k] = h[k]

    return list(rows.values())


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

            df = fetch_meta_timeseries(ticker=ticker_only, exchange=exchange,
                                        start_date=cutoff, end_date=today)

            if df is not None and not df.empty:
                latest_row = df.iloc[-1]
                snapshot[t] = {
                    "last_price":     float(latest_row["close"]),
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
    from backend.common.alerts import publish_alert

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
                publish_alert(alert)
                alerts.append(alert)
    return alerts
