# backend/routes/instrument.py
from __future__ import annotations

"""
Instrument (single-ticker) API routes.

Examples
--------
GET /instrument?ticker=XDEV.L&days=365&format=json
GET /instrument?ticker=XDEV.L&days=365&format=html
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.common.instruments import list_instruments
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import get_security_meta
from backend.common.instrument_api import intraday_timeseries_for_ticker
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import apply_scaling, get_scaling_override
from backend.utils.fx_rates import fetch_fx_rate_range
from backend.config import config

templates_dir = Path(__file__).resolve().parent.parent / "templates"
env = Environment(
    loader=FileSystemLoader(templates_dir),
    autoescape=select_autoescape(["html", "xml"]),
)

# Group the instrument endpoints under their own router to keep ``app.py``
# tidy and allow reuse across different deployment targets.
router = APIRouter(prefix="/instrument", tags=["instrument"])

MAX_SEARCH_RESULTS = 20


@router.get("/search")
async def search_instruments(
    q: str | None = Query(None, description="Search term for ticker or name"),
    sector: str | None = Query(None),
    region: str | None = Query(None),
):
    if not q or not q.strip():
        raise HTTPException(400, "query is required")
    if sector is not None and not sector.strip():
        raise HTTPException(400, "sector must be non-empty")
    if region is not None and not region.strip():
        raise HTTPException(400, "region must be non-empty")

    q_lower = q.strip().lower()
    sector_lower = sector.strip().lower() if sector else None
    region_lower = region.strip().lower() if region else None

    matches: list[dict[str, Any]] = []
    for inst in list_instruments():
        ticker = inst.get("ticker") or ""
        name = inst.get("name") or ""
        if q_lower not in ticker.lower() and q_lower not in name.lower():
            continue
        if sector_lower and (inst.get("sector") or "").lower() != sector_lower:
            continue
        if region_lower and (inst.get("region") or "").lower() != region_lower:
            continue
        matches.append(
            {
                "ticker": ticker,
                "name": name,
                "sector": inst.get("sector"),
                "region": inst.get("region"),
            }
        )
        if len(matches) >= MAX_SEARCH_RESULTS:
            break
    return matches


# ────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────
def _validate_ticker(tkr: str) -> None:
    """Basic sanity checks for user supplied tickers.

    ``XDEV.L`` is valid whereas ``.L`` or ``.UK`` are rejected. This is mainly a
    guard against empty or malformed inputs that would otherwise result in large
    upstream downloads.
    """

    if not tkr or tkr in {".L", ".UK"}:
        raise HTTPException(400, f'Invalid ticker: "{tkr}"')


def _positions_for_ticker(tkr: str, last_close: float | None) -> List[Dict[str, Any]]:
    """Return every occurrence of ``tkr`` across all portfolios.

    The structure returned by :func:`list_portfolios` looks roughly like::

        {
          "owner": "alex",
          "accounts": [
              {"account_type": "isa",  "holdings": [...]},
              {"account_type": "sipp", "holdings": [...]},
          ]
        }

    This helper walks the nested tree and flattens all matching holdings into a
    list of simple dictionaries.
    """

    positions: List[Dict[str, Any]] = []

    # Iterate through owners -> accounts -> holdings
    for pf in list_portfolios():
        owner = pf["owner"]
        for acct in pf.get("accounts", []):
            acct_name = acct.get("account_type", "account")
            for h in acct.get("holdings", []):
                if (h.get("ticker") or "").upper() != tkr:
                    continue

                units = h.get("units") or h.get("quantity")
                mv_gbp = None if units is None or last_close is None else round(units * last_close, 2)

                gain_gbp = h.get("gain_gbp")
                gain_pct = h.get("gain_pct")
                if gain_gbp is None and mv_gbp is not None:
                    # fall back to cost basis when explicit gain is missing
                    cost = h.get("effective_cost_basis_gbp") or h.get("cost_basis_gbp") or h.get("cost_basis")
                    try:
                        cost_f = float(cost) if cost is not None else None
                    except (TypeError, ValueError):
                        cost_f = None
                    if cost_f is not None:
                        gain_gbp = round(mv_gbp - cost_f, 2)
                        gain_pct = (gain_gbp / cost_f * 100.0) if cost_f else None

                positions.append(
                    {
                        "owner": owner,
                        "account": acct_name,
                        "units": units,
                        "market_value_gbp": mv_gbp,
                        "unrealised_gain_gbp": gain_gbp,
                        "gain_pct": gain_pct,
                    }
                )
    return positions


def _as_iso(d) -> str:
    """Return ``d`` as a simple ``YYYY-MM-DD`` string."""

    if isinstance(d, (pd.Timestamp, date)):
        return d.date().isoformat() if isinstance(d, pd.Timestamp) else d.isoformat()
    return str(d)[:10]


def _render_html(
    ticker: str,
    df: pd.DataFrame,
    positions: List[Dict[str, Any]],
    window_days: int,
) -> str:
    """Render a minimal HTML page summarising price and position data."""
    prices_tbl = df[["Date", "Close"]].tail(30).to_html(index=False, classes="prices")
    pos_tbl = pd.DataFrame(positions).to_html(index=False, classes="positions") if positions else None

    begin, end = _as_iso(df.iloc[0]["Date"]), _as_iso(df.iloc[-1]["Date"])

    template = env.get_template("instrument.html")
    return template.render(
        ticker=ticker,
        window_days=window_days,
        prices_tbl=prices_tbl,
        pos_tbl=pos_tbl,
        begin=begin,
        end=end,
        rows_count=f"{len(df):,}",
        today=date.today().isoformat(),
    )


# ────────────────────────────────────────────────────────────────
# route
# ────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def instrument(
    ticker: str = Query(..., description="Full ticker, e.g. VWRL.L"),
    days: int = Query(365, ge=0, le=36500),
    format: str = Query("html", pattern="^(html|json)$"),
    base_currency: str | None = Query(
        None, description="Reporting currency for prices"
    ),
):
    """Return price history and portfolio positions for a ticker.

    Depending on ``format`` the response is either a small HTML page or a JSON
    payload that includes the price history plus all the holdings where the
    instrument appears.
    """

    _validate_ticker(ticker)

    if days <= 0:
        start = date(1900, 1, 1)
    else:
        start = date.today() - timedelta(days=days)
    tkr, exch = (ticker.split(".", 1) + ["L"])[:2]

    # ── history ────────────────────────────────────────────────
    df = load_meta_timeseries_range(tkr, exch, start_date=start, end_date=date.today())
    if df.empty:
        raise HTTPException(404, f"No price data for {ticker}")

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])

    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Ensure Close column exists for downstream processing
    if "Close" not in df.columns and "Close_gbp" in df.columns:
        df["Close"] = df["Close_gbp"]

    meta = get_security_meta(ticker) or {}
    name = meta.get("name")
    sector = meta.get("sector")
    currency = meta.get("currency")

    base_currency = (
        base_currency or getattr(config, "base_currency", None) or "GBP"
    ).upper()

    ts_is_gbp = currency == "GBP" or "Close_gbp" in df.columns
    if ts_is_gbp and "Close_gbp" not in df.columns and "Close" in df.columns:
        df["Close_gbp"] = df["Close"]

    # Apply instrument-specific scaling
    scale = get_scaling_override(tkr, exch, None)
    if scale != 1.0:
        df = apply_scaling(df, scale)
        if "Close_gbp" in df.columns:
            df["Close_gbp"] = pd.to_numeric(df["Close_gbp"], errors="coerce") * scale

    df = df[pd.notnull(df["Close"])]

    last_close = float(df.iloc[-1]["Close_gbp"]) if "Close_gbp" in df.columns else None
    positions = _positions_for_ticker(ticker.upper(), last_close)

    if scale != 1.0:
        for p in positions:
            if p.get("unrealised_gain_gbp") is not None:
                p["unrealised_gain_gbp"] = p["unrealised_gain_gbp"] * scale

    # ── JSON ───────────────────────────────────────────────────
    if format == "json":
        cols = ["Date", "Close"]
        rename = {"Date": "date", "Close": "close"}
        assigns = {
            "date": lambda d: d["date"].dt.strftime("%Y-%m-%d"),
            "close": lambda d: d["close"].astype(float),
        }
        fx_links: Dict[str, str] = {}

        is_gbp_ticker = ticker.upper().endswith(".L") or ticker.upper().endswith(".UK")
        if currency == "GBX" or (currency is None and is_gbp_ticker):
            currency = "GBP"
        if "Close_gbp" not in df.columns and "Close" in df.columns and (currency == "GBP" or is_gbp_ticker):
            df["Close_gbp"] = df["Close"]

        if currency not in {"GBP", "GBX"}:
            pair = f"{currency}GBP"
            fx_links[pair] = f"/timeseries/meta?ticker={pair}"

        if "Close_gbp" in df.columns:
            cols.append("Close_gbp")
            rename["Close_gbp"] = "close_gbp"
            assigns["close_gbp"] = lambda d: d["close_gbp"].astype(float)
            currency = "GBP"

        base_lower = base_currency.lower()
        if base_currency != currency:
            if "Close_gbp" not in df.columns:
                df["Close_gbp"] = df["Close"]
            start_fx = df["Date"].dt.date.min()
            end_fx = df["Date"].dt.date.max()
            try:
                fx = fetch_fx_rate_range(base_currency, start_fx, end_fx)
                if not fx.empty:
                    fx["Date"] = pd.to_datetime(fx["Date"])
                    df = df.merge(fx, on="Date", how="left")
                    col_name = f"Close_{base_lower}"
                    df[col_name] = df["Close_gbp"] / pd.to_numeric(df["Rate"], errors="coerce")
                    df.drop(columns=["Rate"], inplace=True)
                    cols.append(col_name)
                    rename[col_name] = f"close_{base_lower}"
                    assigns[f"close_{base_lower}"] = (
                        lambda d, c=f"close_{base_lower}": d[c].astype(float)
                    )
                    pair = f"{base_currency}GBP"
                    fx_links[pair] = f"/timeseries/meta?ticker={pair}"
            except Exception:
                pass

        prices = (
            df[cols]
            .rename(columns=rename)
            .assign(**assigns)
            .to_dict(orient="records")
        )
        mini = {"7": prices[-7:], "30": prices[-30:], "180": prices[-180:]}
        payload = {
            "ticker": ticker,
            "from": start.isoformat(),
            "to": date.today().isoformat(),
            "rows": len(prices),
            "positions": positions,
            "prices": prices,
            "mini": mini,
            "currency": currency,
            "name": name,
            "sector": sector,
            "base_currency": base_currency,
        }
        if fx_links:
            payload["fx"] = fx_links
        return JSONResponse(jsonable_encoder(payload))

    # ── HTML ───────────────────────────────────────────────────
    window_days = days if days > 0 else (df["Date"].dt.date.max() - df["Date"].dt.date.min()).days + 1
    return HTMLResponse(
        _render_html(
            ticker=ticker,
            df=df,
            positions=positions,
    window_days=window_days,
        )
    )


@router.get("/intraday")
async def intraday(
    ticker: str = Query(..., description="Full ticker, e.g. VWRL.L")
):
    """Return ~48 hours of intraday prices for ``ticker``."""

    _validate_ticker(ticker)
    payload = intraday_timeseries_for_ticker(ticker)
    return JSONResponse(jsonable_encoder(payload))
