"""
Instrument (single-ticker) API routes.

GET /instrument?ticker=XDEV.L&days=365&format=html
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict, Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from backend.common.portfolio_loader import list_portfolios
from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/instrument", tags=["instrument"])

# ──────────────────────────────────────────────────────────────
# Helper – retrieve *all* positions in *any* portfolio tree that
#           match the supplied ticker (case‑insensitive)
# ──────────────────────────────────────────────────────────────

def _positions_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Return **every** holding whose ``ticker`` matches – irrespective
    of how deeply it is nested inside the portfolio dict.

    The function understands both legacy ``positions`` arrays and the
    newer ``holdings`` layout used in ``data/accounts/<owner>`` files.
    """

    ticker = ticker.upper()
    results: List[Dict[str, Any]] = []

    def _walk(node: Any, context: Dict[str, Any]):
        """DFS over dicts/lists – *context* always carries the root
        portfolio meta so we can report owner / portfolio name."""
        if isinstance(node, dict):
            # Heuristic: a single holding MUST contain a ticker key.
            if node.get("ticker", "").upper() == ticker:
                results.append({
                    "owner":     context.get("owner", "—"),
                    "portfolio": context.get("name", context.get("id", "—")),
                    # normalise the most common field names ↓
                    "units":     node.get("quantity") or node.get("units"),
                    "weight":    node.get("weight"),
                })
            # Recurse into children
            for value in node.values():
                _walk(value, context)
        elif isinstance(node, list):
            for item in node:
                _walk(item, context)

    for pf in list_portfolios(lazy=True):  # light‑weight, zero valuations
        _walk(pf, pf)                      # context == top level portfolio

    return results

# ──────────────────────────────────────────────────────────────
# Validation helper
# ──────────────────────────────────────────────────────────────

def _validate_ticker(ticker: str) -> None:
    if not ticker or ticker in {".L", ".UK"}:
        raise HTTPException(400, f"Invalid ticker: “{ticker}”")

# ──────────────────────────────────────────────────────────────
# Tiny in‑file HTML renderer
# ──────────────────────────────────────────────────────────────

def _as_iso(d) -> str:
    """Return YYYY‑MM‑DD from either date, Timestamp or str."""
    if isinstance(d, (date, pd.Timestamp)):
        return d.date().isoformat() if isinstance(d, pd.Timestamp) else d.isoformat()
    return str(d)[:10]


def _render_html_page(
    ticker: str,
    df: pd.DataFrame,
    positions: List[Dict[str, Any]],
    window_days: int,
) -> str:
    prices_tbl = (
        df[["Date", "Close"]]
          .tail(30)
          .to_html(index=False, classes="prices")
    )

    pos_tbl = (
        pd.DataFrame(positions).to_html(index=False, classes="positions")
        if positions else "<p>No portfolio positions</p>"
    )

    start_iso = _as_iso(df.iloc[0]["Date"])
    end_iso   = _as_iso(df.iloc[-1]["Date"])

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
    days:   int = Query(365, ge=30, le=3650),
    format: str = Query("html", pattern="^(html|json)$"),
):
    _validate_ticker(ticker)

    start = date.today() - timedelta(days=days)
    tkr, exch = (ticker.split(".", 1) + ["L"])[0:2]

    df = load_meta_timeseries_range(tkr, exch, start_date=start, end_date=date.today())
    if df.empty:
        raise HTTPException(404, f"No price data for {ticker}")

    positions = _positions_for_ticker(ticker)

    if format == "json":
        return JSONResponse({
            "ticker":    ticker,
            "from":      start.isoformat(),
            "to":        date.today().isoformat(),
            "rows":      len(df),
            "positions": positions,
            "prices":    df.to_dict(orient="records"),
        })

    html = _render_html_page(
        ticker=ticker,
        df=df,
        positions=positions,
        window_days=days,
    )
    return HTMLResponse(html)
