import logging
import re
from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pandas.api import types as pd_types

from backend.common import instrument_api
from backend.logging_setup import sanitise_log_value
from backend.timeseries import fetch_timeseries
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.html_render import render_timeseries_html
from backend.utils.timeseries_helpers import (
    apply_scaling,
    get_scaling_override,
    resolve_date_range,
)

router = APIRouter(prefix="/timeseries", tags=["timeseries"])
logger = logging.getLogger("routes.timeseries")

# Only A-Z, 0-9, and hyphens are valid in a ticker segment or exchange code.
# This allowlist prevents log injection from flowing into any log sink (CWE-117).
_TICKER_SEGMENT_RE = re.compile(r"^[A-Z0-9-]{1,20}$")


def _resolve_ticker_exchange(ticker: str, exchange: str | None) -> tuple[str, str]:
    t = (ticker or "").upper()
    if not t:
        raise HTTPException(status_code=400, detail="Ticker is required")

    if exchange:
        sym = t.split(".", 1)[0]
        ex = exchange.upper()
        source = "provided exchange"
    elif "." in t:
        sym, ex = t.split(".", 1)
        source = "inferred from ticker"
    else:
        resolved = instrument_api._resolve_full_ticker(
            t, instrument_api._LATEST_PRICES
        )
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail="Exchange not provided and could not be inferred",
            )
        sym, ex = resolved
        source = "inferred exchange"

    # Validate before logging — sym/ex are [A-Z0-9-] only after this point (CWE-117).
    if not _TICKER_SEGMENT_RE.match(sym) or not _TICKER_SEGMENT_RE.match(ex):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    logger.debug("Resolved %s.%s (%s)", sanitise_log_value(sym), sanitise_log_value(ex), source)
    return sym, ex


@router.get("/meta", response_class=HTMLResponse)
async def get_meta_timeseries(
    ticker: str = Query(...),
    exchange: str | None = Query(None),
    days: int = Query(365, ge=0, le=36500),
    format: str = Query("html", pattern="^(html|json|csv)$"),
    scaling: float = Query(1.0, ge=0.00001, le=1_000_000),
    start_date: date | None = Query(
        None, description="Start date (YYYY-MM-DD). Overrides days when provided."
    ),
    end_date: date | None = Query(
        None, description="End date (YYYY-MM-DD). Defaults to yesterday when omitted."
    ),
):
    ticker, exchange = _resolve_ticker_exchange(ticker, exchange)

    start_date, end_date = resolve_date_range(
        days, start_date=start_date, end_date=end_date
    )

    # 422 matches FastAPI's convention for parameter validation errors (issue #2747 AC).
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail=f"start_date ({start_date}) must not be after end_date ({end_date})",
        )

    try:
        df = load_meta_timeseries_range(
            ticker, exchange, start_date=start_date, end_date=end_date
        )
    except Exception as exc:
        logger.debug(
            "Failed to load meta timeseries for %s.%s: %s",
            sanitise_log_value(ticker), sanitise_log_value(exchange), sanitise_log_value(exc),
        )
        raise HTTPException(
            status_code=404, detail="timeseries meta not found"
        ) from exc

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="timeseries meta not found")

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    # ── Apply scaling if requested ─────────────────────────────
    if scaling != 1.0:
        for col in ("Open", "High", "Low", "Close"):
            if col in df.columns:
                df[col] = df[col] * scaling

    # ── JSON output ───────────────────────────────────────────
    if format == "json":
        datetime_columns = [
            col for col in df.columns if pd_types.is_datetime64_any_dtype(df[col])
        ]
        for col in datetime_columns:
            df[col] = df[col].map(lambda x: x.isoformat() if pd.notnull(x) else None)
        return JSONResponse(
            content={
                "ticker": f"{ticker}.{exchange}",
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "scaling": scaling,
                "prices": df.to_dict(orient="records"),
            }
        )

    # ── CSV output (plain `if`, not `elif` — JSON path returns above) ─────
    if format == "csv":
        return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")

    # ── HTML output (default) ─────────────────────────────────
    return _render_meta_html(df, ticker, exchange, start_date, end_date, scaling)


def _render_meta_html(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
    scaling: float,
) -> HTMLResponse:
    """Render the meta timeseries as HTML using the shared render helper.

    Pads any missing standard columns with safe defaults so
    render_timeseries_html never raises KeyError on this DataFrame.
    """
    render_df = df.copy()
    for col in ("Open", "High", "Low", "Close"):
        if col not in render_df.columns:
            render_df[col] = float("nan")
    if "Volume" not in render_df.columns:
        render_df["Volume"] = 0
    if "Ticker" not in render_df.columns:
        render_df["Ticker"] = f"{ticker}.{exchange}"
    if "Source" not in render_df.columns:
        render_df["Source"] = "meta"

    subtitle = f"{start_date} to {end_date}"
    if scaling != 1.0:
        subtitle = f"{subtitle} (scaling: {scaling}x)"

    return render_timeseries_html(
        render_df,
        f"{ticker}.{exchange} Price History",
        subtitle,
    )


@router.get("/html", response_class=HTMLResponse)
async def yahoo_timeseries_html(
    ticker: str = Query(...),
    period: str = Query("1y"),
    interval: str = Query("1d"),
    scaling: float | None = Query(None, ge=0.00001, le=1_000_000),
):
    try:
        df = fetch_timeseries.fetch_yahoo_timeseries(ticker, period, interval)
    except Exception:
        df = pd.DataFrame(
            [
                {
                    "Date": date.today(),
                    "Open": 0.0,
                    "High": 0.0,
                    "Low": 0.0,
                    "Close": 0.0,
                    "Volume": 0,
                    "Ticker": ticker,
                    "Source": "Yahoo",
                }
            ]
        )

    scale = get_scaling_override(ticker, "", scaling)
    df = apply_scaling(df, scale)
    if "Source" not in df.columns:
        df["Source"] = "Yahoo"
    if "Ticker" not in df.columns:
        df["Ticker"] = ticker
    return render_timeseries_html(df, f"{ticker} Price History", f"{period} - {interval}")