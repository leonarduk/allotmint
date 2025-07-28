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

@app.get("/timeseries/html", response_class=HTMLResponse)
async def get_timeseries_html(
    ticker: str = Query(...),
    period: str = Query("1y"),
    interval: str = Query("1d")
):
    try:
        df = fetch_yahoo_timeseries(ticker, period=period, interval=interval)
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)

    if df.empty:
        return HTMLResponse("<h1>No data found</h1>", status_code=404)

    # Only show desired columns
    df = df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]]

    # Apply consistent formatting
    df["Volume"] = df["Volume"].apply(lambda x: f"{int(x):,}")
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].map("{:.2f}".format)

    html_table = df.to_html(index=False, classes="table table-striped text-center", border=0)

    return HTMLResponse(content=f"""
    <html>
    <head>
        <title>Time Series for {ticker}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body {{ padding: 2rem; }}
            table {{ font-size: 0.9rem; }}
            th, td {{ vertical-align: middle; }}
            h2 small {{ font-size: 1rem; color: #666; }}
        </style>
    </head>
    <body>
        <h2>Time Series for <code>{ticker}</code><br><small>{period} / {interval}</small></h2>
        {html_table}
    </body>
    </html>
    """)


@app.get("/timeseries/ft", response_class=HTMLResponse)
def get_ft_timeseries(
    ticker: str = Query(..., description="FT.com ticker e.g. GB00B45Q9038:GBP"),
    days: int = Query(365, description="Number of days of history to fetch"),
    format: str = Query("html", description="Response format: html, csv, or json")
):
    try:
        df = fetch_ft_timeseries(ticker, days=days)

        if format == "json":
            return JSONResponse(content=df.to_dict(orient="records"))

        elif format == "csv":
            return PlainTextResponse(content=df.to_csv(index=False), media_type="text/csv")

        # Default: HTML table
        html_table = df.to_html(index=False, justify="center", border=0)
        return HTMLResponse(content=f"<h2>{ticker} - Last {days} Days</h2>{html_table}")

    except Exception as e:
        return HTMLResponse(content=f"<h3>Error: {str(e)}</h3>", status_code=500)
