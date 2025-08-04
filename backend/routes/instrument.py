"""
/instrument endpoint with HTML chart + positions table or JSON.

Example:
    /instrument?ticker=XDEV.L&days=365          (HTML)
    /instrument?ticker=XDEV.L&days=365&format=json
"""

from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    aggregate_by_ticker,
    list_all_unique_tickers,
)
from backend.timeseries.cache import load_meta_timeseries

log = logging.getLogger("routes.instrument")
router = APIRouter(tags=["instrument"])


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _snapshot_row(ticker: str) -> dict | None:
    """Return aggregated snapshot for ticker (price, gain, …)."""
    ticker = ticker.upper()
    for pf in list_portfolios():
        for row in aggregate_by_ticker(pf):
            if row["ticker"] == ticker:
                return row
    return None


def _positions_for_ticker(ticker: str) -> List[dict]:
    """
    Collect every individual position (owner / account / units / cost / value)
    across all portfolios.
    """
    out: List[dict] = []
    for pf in list_portfolios():
        owner = pf["owner"]
        for acct in pf.get("accounts", []):
            account_name = acct["account"]
            for h in acct.get("holdings", []):
                if (h.get("ticker") or "").upper() == ticker.upper():
                    out.append(
                        {
                            "owner": owner,
                            "account": account_name,
                            "units": h.get("units", 0.0),
                            "cost_gbp": h.get("cost_gbp", 0.0),
                            "market_value_gbp": h.get("market_value_gbp", 0.0),
                        }
                    )
    return out


def _html_page(row: dict, prices: List[dict], positions: List[dict]) -> str:
    """Return a self-contained HTML page with Chart.js + table."""
    chart_data = [
        {"x": p["Date"], "y": p["Close"]} for p in prices
    ]
    title = f"{row['ticker']} — {row.get('name', '')}"
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin:2rem; }}
    table {{ border-collapse: collapse; width:100%; margin-top:2rem; }}
    th,td {{ border:1px solid #ccc; padding:.4rem .6rem; text-align:right; }}
    th {{ background:#f0f0f0; }}
    td:first-child,th:first-child {{ text-align:left; }}
  </style>
</head>
<body>
  <h2>{title}</h2>
  <canvas id="priceChart" height="120"></canvas>
  <script>
    const ctx = document.getElementById("priceChart").getContext("2d");
    new Chart(ctx,{{
      type:"line",
      data:{{datasets:[{{label:"Close (£)",data:{json.dumps(chart_data)},fill:false}}]}},
      options:{{responsive:true, parsing:{{xAxisKey:"x",yAxisKey:"y"}}, scales:{{x:{{type:"time",time:{{unit:"month"}}}}}}}}
    }});
  </script>

  <h3>Positions</h3>
  <table>
    <thead>
      <tr><th>Owner</th><th>Account</th><th>Units</th>
          <th>Cost (£)</th><th>Value (£)</th></tr>
    </thead>
    <tbody>
      {"".join(
        f"<tr><td>{p['owner']}</td><td>{p['account']}</td>"
        f"<td>{p['units']:.2f}</td><td>{p['cost_gbp']:.2f}</td>"
        f"<td>{p['market_value_gbp']:.2f}</td></tr>"
        for p in positions
      )}
    </tbody>
  </table>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────
@router.get("/instrument")
async def instrument(
    ticker: str = Query(..., description="Exact ticker, e.g. XDEV.L"),
    days: int = Query(365, ge=30, le=1825),
    format: str = Query("html", pattern="^(html|json)$"),
):
    ticker = ticker.upper()

    if ticker not in list_all_unique_tickers():
        raise HTTPException(status_code=404, detail="Ticker not in portfolios")

    row = _snapshot_row(ticker)
    if not row:
        raise HTTPException(status_code=404, detail="Ticker held nowhere")

    try:
        ts_df = load_meta_timeseries(ticker, "L", days)
        prices = [
            {"Date": str(r.Date), "Close": float(r.Close)}
            for r in ts_df[["Date", "Close"]].itertuples(index=False)
        ]
    except Exception as exc:
        log.warning("Timeseries fetch failed for %s: %s", ticker, exc)
        prices = []

    positions = _positions_for_ticker(ticker)

    if format == "json":
        return JSONResponse({**row, "prices": prices, "positions": positions})

    # html
    return HTMLResponse(_html_page(row, prices, positions))
