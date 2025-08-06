from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from datetime import date, timedelta
import pandas as pd

from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/timeseries", tags=["timeseries"])

@router.get("/meta", response_class=HTMLResponse)
async def get_meta_timeseries(
    ticker: str = Query(...),
    exchange: str = Query("L"),
    days: int = Query(365, ge=30, le=3650),
    format: str = Query("html", regex="^(html|json|csv)$"),
    scaling: float = Query(1.0, ge=0.00001, le=1_000_000),
):
    start_date = date.today() - timedelta(days=days)
    end_date = date.today() - timedelta(days=1)

    try:
        df = load_meta_timeseries_range(ticker, exchange, start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {ticker}.{exchange}")

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
        return JSONResponse(content={
            "ticker": f"{ticker}.{exchange}",
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "scaling": scaling,
            "prices": df.to_dict(orient="records"),
        })

    # ── CSV output ────────────────────────────────────────────
    elif format == "csv":
        csv_text = df.to_csv(index=False)
        return PlainTextResponse(content=csv_text, media_type="text/csv")

    # ── HTML output (default) ─────────────────────────────────
    html_table = df.to_html(index=False)
    html_doc = f"""
    <html>
        <head><title>{ticker}.{exchange} Price History</title></head>
        <body>
            <h1>{ticker}.{exchange} - {start_date} to {end_date}</h1>
            <p><strong>Scaling:</strong> {scaling}x</p>
            {html_table}
        </body>
    </html>
    """
    return HTMLResponse(content=html_doc)
