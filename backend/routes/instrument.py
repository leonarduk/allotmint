"""
Instrument (single-ticker) API routes.

Example:
    GET /instrument?ticker=XDEV.L&days=365&format=json
    GET /instrument?ticker=XDEV.L&days=365&format=html
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from backend.common.portfolio_loader import _portfolio_files, list_portfolios
from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/instrument", tags=["instrument"])

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _positions_for_ticker(ticker: str, last_close: float) -> list[dict]:
    """Collect every holding of *ticker* across every owner/portfolio."""
    positions: list[dict] = []
    src_paths = _portfolio_files()

    for pf, src in zip(list_portfolios(lazy=True), src_paths):
        for pos in pf.get("positions", []) + pf.get("holdings", []):
            if pos.get("ticker") != ticker:
                continue

            units = pos.get("quantity", pos.get("units"))
            mv_gbp = units * last_close if units is not None else None

            positions.append(
                {
                    "owner": pf.get("owner", "—"),
                    "portfolio": pf.get("name")
                    or pf.get("id")
                    or Path(src).stem,
                    "units": units,
                    "weight": pos.get("weight", ""),
                    "market_value_gbp": mv_gbp,
                    "unrealised_gain_gbp": pos.get("gain_gbp", None),
                }
            )
    return positions


def _validate_ticker(ticker: str) -> None:
    if not ticker or ticker in {".L", ".UK"}:
        raise HTTPException(400, f"Invalid ticker: “{ticker}”")


# ──────────────────────────────────────────────────────────────
# Tiny in-file HTML renderer
# ──────────────────────────────────────────────────────────────
def _as_iso(d) -> str:
    if isinstance(d, pd.Timestamp):
        d = d.date()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def _render_html_page(
    ticker: str,
    df: pd.DataFrame,
    positions: List[Dict[str, Any]],
    window_days: int,
) -> str:
    prices_tbl = (
        df[["Date", "Close"]].tail(30).to_html(index=False, classes="prices")
    )

    pos_tbl = (
        pd.DataFrame(positions).to_html(index=False, classes="positions")
        if positions
        else "<p>No portfolio positions</p>"
    )

    start_iso = _as_iso(df.iloc[0]["Date"])
    end_iso = _as_iso(df.iloc[-1]["Date"])

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{ticker} • {window_days}-day view</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    h1  {{ margin-bottom: .25rem; }}
    table {{ border-collapse: collapse; margin-top: .5rem; }}
    th, td {{ padding: .25rem .5rem; border: 1px solid #ccc; }}
    th {{ background: #f5f5f5; }}
    .prices    {{ float: left; margin-right: 2rem; }}
    .positions {{ float: left; }}
    footer {{ clear: both; margin-top: 3rem; font-size: .85em; color: #666; }}
  </style>
</head>
<body>
  <h1>{ticker}</h1>
  <p>{len(df):,} rows • {start_iso} → {end_iso}</p>

  <section>{prices_tbl}</section>
  <section>{pos_tbl}</section>

  <footer>Generated {date.today().isoformat()}</footer>
</body>
</html>
""".strip()


# ──────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def instrument(
    ticker: str = Query(..., description="Full ticker, e.g. VWRL.L"),
    days: int = Query(365, ge=30, le=3650),
    format: str = Query("html", pattern="^(html|json)$"),
):
    _validate_ticker(ticker)

    start = date.today() - timedelta(days=days)
    tkr, exch = (ticker.split(".", 1) + ["L"])[:2]

    # ── Price history ──────────────────────────────────────────
    df = load_meta_timeseries_range(tkr, exch, start_date=start, end_date=date.today())
    if df.empty:
        raise HTTPException(404, f"No price data for {ticker}")

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])

    # Unify column name: make sure we have “Close”
    if "Close_gbp" in df.columns:
        df.rename(columns={"Close_gbp": "Close"}, inplace=True)

    # Remove rows where the close price is NaN / ±Inf
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df[pd.notnull(df["Close"])]

    last_close = float(df.iloc[-1]["Close"])
    positions = _positions_for_ticker(ticker, last_close)

    # ── JSON variant ───────────────────────────────────────────
    if format == "json":
        prices = (
            df[["Date", "Close"]]
            .rename(columns={"Date": "date", "Close": "close_gbp"})
            .assign(
                date=lambda d: d["date"].dt.strftime("%Y-%m-%d"),
                close_gbp=lambda d: d["close_gbp"].astype(float),
            )
            .to_dict(orient="records")
        )

        payload = {
            "ticker": ticker,
            "from": start.isoformat(),
            "to": date.today().isoformat(),
            "rows": len(prices),
            "positions": positions,
            "prices": prices,
        }
        return JSONResponse(jsonable_encoder(payload))

    # ── HTML variant ───────────────────────────────────────────
    html = _render_html_page(
        ticker=ticker,
        df=df,
        positions=positions,
        window_days=days,
    )
    return HTMLResponse(html)
