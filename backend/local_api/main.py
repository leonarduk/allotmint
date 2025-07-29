import logging
import os

from fastapi import FastAPI, Query
from fastapi import HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.common.data_loader import list_plots, load_account
from backend.common.group_portfolio import list_groups
from backend.common.instrument_api import timeseries_for_ticker, positions_for_ticker
from backend.common.portfolio import build_owner_portfolio
from backend.common.prices import refresh_prices
from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries
from backend.timeseries.fetch_timeseries import fetch_yahoo_timeseries

logging.basicConfig(level=logging.DEBUG)


app = FastAPI(title="AllotMint Local API", version="0.1")

# DEV-ONLY: allow all origins so Vite (5173) can call backend (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # in prod: replace with specific domain(s)
    allow_methods=["*"],
    allow_headers=["*"],
)

os.environ.setdefault("ALLOTMINT_ENV", "local")


@app.get("/health")
def health():
    return {"status": "ok", "env": os.getenv("ALLOTMINT_ENV", "local")}


@app.get("/owners")
def owners():
    return list_plots()

@app.get("/groups")
def groups():
    return list_groups()

@app.get("/portfolio-group/{group_name}")
def portfolio_group(group_name: str):
    try:
        return build_group_portfolio(group_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Group not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/portfolio/{owner}")
def portfolio(owner: str):
    try:
        return build_owner_portfolio(owner)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/account/{owner}/{account}")
def get_account(owner: str, account: str):
    try:
        return load_account(owner, account)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/prices/refresh")
def prices_refresh():
    try:
        summary = refresh_prices()
        return {"status": "ok", **summary}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))

from backend.common.group_portfolio import build_group_portfolio
from backend.common.portfolio_utils import aggregate_by_ticker

@app.get("/portfolio-group/{slug}/instruments")
def group_by_instrument(slug: str):
    gp = build_group_portfolio(slug)
    return aggregate_by_ticker(gp)

@app.get("/portfolio-group/{slug}/instruments")
def group_instruments(slug: str):
    """
    One row per ticker across the whole group, enriched with
    last price and % changes.
    """
    gp = build_group_portfolio(slug)
    return aggregate_by_ticker(gp)


@app.get("/portfolio-group/{slug}/instrument/{ticker}")
def instrument_detail(slug: str, ticker: str, days: int = 365):
    prices = timeseries_for_ticker(ticker.upper(), days)
    if not prices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price history for {ticker.upper()}",
        )
    return {
        "prices": prices,
        "positions": positions_for_ticker(slug, ticker.upper()),
    }

from backend.utils.html_render import render_timeseries_html

@app.get("/timeseries/html", response_class=HTMLResponse)
async def get_timeseries_html(
    ticker: str = Query(...),
    period: str = Query("1y"),
    interval: str = Query("1d")
):
    try:
        df = fetch_yahoo_timeseries(ticker, period=period, interval=interval)
        if df.empty:
            return HTMLResponse("<h1>No data found</h1>", status_code=404)

        return render_timeseries_html(df, f"Time Series for {ticker}", f"{period} / {interval}")

    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)

@app.get("/timeseries/ft", response_class=HTMLResponse)
def get_ft_timeseries(
    ticker: str = Query(..., description="FT.com ticker e.g. GB00B45Q9038:GBP"),
    period: str = Query("1y", description="e.g. 1y, 6mo, 3mo"),
    interval: str = Query("1d", description="Unused for FT but accepted for consistency"),
    format: str = Query("html", description="html | json | csv")
):
    try:
        # Convert period string to number of days (basic mapping)
        period_map = {
            "1d": 1,
            "5d": 5,
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
            "5y": 1825,
            "10y": 3650
        }
        days = period_map.get(period, 365)

        df = fetch_ft_timeseries(ticker, days=days)
        if df.empty:
            return HTMLResponse("<h1>No data found</h1>", status_code=404)

        if format == "json":
            return JSONResponse(content=df.to_dict(orient="records"))

        elif format == "csv":
            return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")

        return render_timeseries_html(df, f"FT Time Series for {ticker}", f"{period} / {interval}")

    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)
