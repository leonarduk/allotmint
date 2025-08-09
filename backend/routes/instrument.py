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
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from backend.common.portfolio_loader import list_portfolios
from backend.timeseries.cache import load_meta_timeseries_range
from backend.common.portfolio_utils import get_security_meta

# Group the instrument endpoints under their own router to keep ``app.py``
# tidy and allow reuse across different deployment targets.
router = APIRouter(prefix="/instrument", tags=["instrument"])

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


def _positions_for_ticker(tkr: str, last_close: float) -> List[Dict[str, Any]]:
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
                mv_gbp = None if units is None else round(units * last_close, 2)

                positions.append(
                    {
                        "owner": owner,
                        "account": acct_name,
                        "units": units,
                        "market_value_gbp": mv_gbp,
                        "unrealised_gain_gbp": h.get("gain_gbp"),
                        "gain_pct": h.get("gain_pct"),
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
    pos_tbl = (
        pd.DataFrame(positions).to_html(index=False, classes="positions")
        if positions
        else "<p>No portfolio positions</p>"
    )

    begin, end = _as_iso(df.iloc[0]["Date"]), _as_iso(df.iloc[-1]["Date"])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{ticker} - {window_days}-day view</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    table{{ border-collapse:collapse;margin:.5rem 0}}
    th,td{{ padding:.25rem .5rem;border:1px solid #ccc; }}
    th{{background:#f5f5f5}}
    .prices{{ float:left;margin-right:2rem }}
    footer{{ clear:both;margin-top:3rem;font-size:.85em;color:#666 }}
  </style>
</head>
<body>
  <h1>{ticker}</h1>
  <p>{len(df):,} rows - {begin} -> {end}</p>

  <section>{prices_tbl}</section>
  <section>{pos_tbl}</section>

  <footer>Generated {date.today().isoformat()}</footer>
</body>
</html>"""


# ────────────────────────────────────────────────────────────────
# route
# ────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def instrument(
    ticker: str = Query(..., description="Full ticker, e.g. VWRL.L"),
    days: int = Query(365, ge=0, le=36500),
    format: str = Query("html", pattern="^(html|json)$"),
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

    # Ensure both Close and Close_gbp columns exist
    if "Close" not in df.columns and "Close_gbp" in df.columns:
        df["Close"] = df["Close_gbp"]
    if "Close_gbp" not in df.columns and "Close" in df.columns:
        df["Close_gbp"] = df["Close"]

    df = df[pd.notnull(df["Close"])]

    last_close = float(df.iloc[-1]["Close_gbp"])
    positions = _positions_for_ticker(ticker.upper(), last_close)

    # ── JSON ───────────────────────────────────────────────────
    if format == "json":
        prices = (
            df[["Date", "Close", "Close_gbp"]]
            .rename(columns={"Date": "date", "Close": "close", "Close_gbp": "close_gbp"})
            .assign(
                date=lambda d: d["date"].dt.strftime("%Y-%m-%d"),
                close=lambda d: d["close"].astype(float),
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
            "currency": (get_security_meta(ticker) or {}).get("currency"),
        }
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
