"""
Instrument (single-ticker) API routes.

GET /instrument?ticker=XDEV.L&days=365&format=html
"""
from __future__ import annotations

from datetime import date, timedelta
from numbers   import Number
from pathlib   import Path
from typing    import Any, Dict, List
import logging
import re

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.common.portfolio_loader import _portfolio_files, list_portfolios
from backend.timeseries.cache        import load_meta_timeseries_range

router = APIRouter(prefix="/instrument", tags=["instrument"])

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
log = logging.getLogger("backend.routes.instrument")

# ──────────────────────────────────────────────────────────────
# Helpers – weight extraction / derivation
# ──────────────────────────────────────────────────────────────
_WEIGHT_KEYS = (
    "weight", "weight_pct", "weight_percent",
    "target_weight", "allocation", "alloc", "alloc_pct",
    "pct", "percentage", "portfolio_weight", "position_weight",
)

def _format_pct(num: float) -> str:
    """Return '7.3 %' (NBSP before %)."""
    return f"{num:.1f}\u00A0%"

def _extract_weight_literal(pos: Dict[str, Any]) -> str | None:
    """Return a prettified weight string *if* a recognised key is present."""
    for key in _WEIGHT_KEYS:
        if key not in pos or pos[key] in (None, ""):
            continue

        raw = pos[key]
        log.debug("   ↳ literal weight %s=%r", key, raw)

        # numbers -------------------------------------------------------------
        if isinstance(raw, Number):
            pct = raw * 100 if raw <= 1 else raw
            return _format_pct(pct)

        # numeric-ish strings -------------------------------------------------
        if isinstance(raw, str):
            cleaned = re.sub(r"[^\d\.]", "", raw)
            if cleaned:
                try:
                    num = float(cleaned)
                    pct = num * 100 if num <= 1 else num
                    return _format_pct(pct)
                except ValueError:
                    pass

        # free-text fallback
        return str(raw)
    return None


def _derive_weight(pos: Dict[str, Any], total_val: float) -> str | None:
    """
    If we have market_value_gbp, derive a % of portfolio.
    total_val is the SUM of market_value_gbp for that portfolio file.
    """
    mv = pos.get("market_value_gbp")
    if not isinstance(mv, Number) or total_val <= 0:
        return None
    pct = mv / total_val * 100
    return _format_pct(pct)


# ──────────────────────────────────────────────────────────────
# Collect every position for the supplied ticker
# ──────────────────────────────────────────────────────────────
def _positions_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """
    Scan **all** portfolio files (lazy mode) and return a list:
       {owner, portfolio, units, weight}
    """
    matches: List[Dict[str, Any]] = []

    for pf, src_path in zip(list_portfolios(lazy=True), _portfolio_files()):
        positions   = pf.get("positions", []) + pf.get("holdings", [])
        total_value = sum(
            p.get("market_value_gbp", 0) for p in positions
            if isinstance(p.get("market_value_gbp"), Number)
        )

        for pos in positions:
            if pos.get("ticker") != ticker:
                continue

            log.debug("Position found in %s → %s", src_path, pos)

            # quantity / units (old + new schema)
            qty = pos.get("quantity", pos.get("units"))

            # 1️⃣ literal weight? … else 2️⃣ derive from market value
            w_str = (
                _extract_weight_literal(pos)
                or _derive_weight(pos, total_value)
                or ""                       # final fallback
            )

            matches.append({
                "owner"    : pf.get("owner", "—"),
                "portfolio": pf.get("name") or pf.get("id") or Path(src_path).stem,
                "units"    : qty,
                "weight"   : w_str,
            })

    log.debug("Collected %d matching positions", len(matches))
    return matches

# ──────────────────────────────────────────────────────────────
# Validation helper
# ──────────────────────────────────────────────────────────────
def _validate_ticker(ticker: str) -> None:
    if not ticker or ticker in {".L", ".UK"}:
        raise HTTPException(400, f"Invalid ticker: “{ticker}”")

# ──────────────────────────────────────────────────────────────
# Tiny in-file HTML renderer
# ──────────────────────────────────────────────────────────────
def _as_iso(d) -> str:
    """Return YYYY-MM-DD from either date, Timestamp or str."""
    if isinstance(d, pd.Timestamp):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def _render_html_page(
    ticker      : str,
    df          : pd.DataFrame,
    positions   : List[Dict[str, Any]],
    window_days : int,
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
    table {{ border-collapse: collapse; margin-top: .5rem; }}
    th, td {{ padding: .25rem .5rem; border: 1px solid #ccc; }}
    th {{ background: #f5f5f5; }}
    .prices    {{ float: left; margin-right: 2rem; }}
    .positions {{ float: left; }}
    footer     {{ clear: both; margin-top: 3rem; font-size: .85em; color: #666; }}
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
    days  : int = Query(365, ge=30, le=3650),
    format: str = Query("html", pattern="^(html|json)$"),
):
    _validate_ticker(ticker)

    start = date.today() - timedelta(days=days)
    tkr, exch = (ticker.split(".", 1) + ["L"])[0:2]

    df = load_meta_timeseries_range(
        tkr, exch,
        start_date=start,
        end_date=date.today(),
    )
    if df.empty:
        raise HTTPException(404, f"No price data for {ticker}")

    positions = _positions_for_ticker(ticker)

    if format == "json":
        return JSONResponse({
            "ticker"   : ticker,
            "from"     : start.isoformat(),
            "to"       : date.today().isoformat(),
            "rows"     : len(df),
            "positions": positions,
            "prices"   : df.to_dict(orient="records"),
        })

    html = _render_html_page(
        ticker      = ticker,
        df          = df,
        positions   = positions,
        window_days = days,
    )
    return HTMLResponse(html)
