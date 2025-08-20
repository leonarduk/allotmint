"""
Light-weight time-series download endpoint for AllotMint.

- Pulls OHLCV data from Yahoo Finance via yfinance
- Streams CSV, returns JSON, **or** renders an HTML table
- Easy to extend with more data sources (Alpha Vantage, Finnhub, ...)
"""

import io
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

router = APIRouter(
    prefix="/timeseries",
    tags=["timeseries"],
    responses={404: {"description": "Ticker not found"}},
)

# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _fetch_yahoo(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance and return a DataFrame."""
    logging.info("Yahoo download | ticker=%s period=%s interval=%s", ticker, period, interval)
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df.empty:
        raise ValueError("No data returned from Yahoo Finance")
    df.reset_index(inplace=True)
    df.insert(0, "Ticker", ticker)
    return df


templates_dir = Path(__file__).resolve().parent.parent / "templates"
env = Environment(
    loader=FileSystemLoader(templates_dir),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_html(df: pd.DataFrame, title: str) -> str:
    """Return a minimal HTML document with a styled table."""
    table_html = df.to_html(classes="dataframe table table-striped", index=False, border=0)
    template = env.get_template("timeseries.html")
    return template.render(title=title, table_html=table_html)


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


@router.get("/{ticker}")
def get_timeseries(
    ticker: str,
    period: str = Query("1y", description="1d, 5d, 1mo, 3mo, 1y, ytd, max ..."),
    interval: str = Query("1d", description="1m, 5m, 15m, 1h, 1d, 1wk, 1mo ..."),
    fmt: str = Query("csv", regex="^(csv|json|html)$", description="csv, json or html table"),
):
    """
    Return a CSV (streamed), JSON, or HTML time-series for *ticker*.

    Example:
        /timeseries/AAPL?period=5y&interval=1wk&fmt=html
    """
    try:
        df = _fetch_yahoo(ticker, period, interval)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # -----------------------------------------------------------------
    # JSON branch
    # -----------------------------------------------------------------
    if fmt == "json":
        records = df.to_dict(orient="records")
        return JSONResponse(jsonable_encoder(records))

    # -----------------------------------------------------------------
    # HTML branch
    # -----------------------------------------------------------------
    if fmt == "html":
        title = f"Time-series for {ticker} ({period}, {interval})"
        html = _render_html(df, title)
        return HTMLResponse(content=html, status_code=200)

    # -----------------------------------------------------------------
    # CSV branch (default)
    # -----------------------------------------------------------------
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"{ticker}_{period}_{interval}_{datetime.utcnow():%Y%m%d}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(buf, media_type="text/csv", headers=headers)
