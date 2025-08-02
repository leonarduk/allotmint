import logging
import os
from typing import Optional

from fastapi import FastAPI, Query
from fastapi import HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from backend.common.data_loader import list_plots, load_account
from backend.common.group_portfolio import list_groups
from backend.common.instrument_api import timeseries_for_ticker, positions_for_ticker
from backend.common.portfolio import build_owner_portfolio
from backend.common.prices import refresh_prices
from backend.utils.cache import (
    load_yahoo_timeseries,
    load_ft_timeseries,
    load_stooq_timeseries, load_meta_timeseries,
)
from backend.utils.period_utils import parse_period_to_days
from backend.utils.timeseries_helpers import apply_scaling, handle_timeseries_response, get_scaling_override

logging.basicConfig(level=logging.DEBUG)

app = FastAPI(title="AllotMint Local API", version="0.1")

# DEV-ONLY: allow all origins so Vite (5173) can call backend (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in prod: replace with specific domain(s)
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
    except Exception as exc:
        logging.exception("Price refresh failed")
        raise HTTPException(status_code=500, detail=f"Price refresh failed: {str(exc)}")


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
    logging.debug(f"Fetching timeseries for {ticker=} in group {slug=}, days={days}")
    prices = timeseries_for_ticker(ticker.upper(), days)

    if not prices:
        logging.warning(f"No price history found for {ticker.upper()}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price history for {ticker.upper()}",
        )

    return {
        "prices": prices,
        "positions": positions_for_ticker(slug, ticker.upper()),
    }


@app.get("/timeseries/ft", response_class=HTMLResponse)
def get_ft_timeseries(
        ticker: str = Query(...),
        exchange: str = Query("L"),
        period: str = Query("1y"),
        interval: str = Query("1d"),
        format: str = Query("html"),
        scaling: Optional[float] = Query(None)
):
    try:
        days = parse_period_to_days(period)
        df = load_ft_timeseries(ticker, exchange, days)
        effective_scaling = get_scaling_override(ticker, exchange, scaling)
        df = apply_scaling(df, effective_scaling)
        return handle_timeseries_response(df, format, f"FT Time Series for {ticker}",
                                          f"{period} / {interval} (×{scaling})")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/timeseries/yahoo", response_class=HTMLResponse)
def get_yahoo_timeseries(
        ticker: str = Query(...),
        exchange: str = Query("L"),
        period: str = Query("1y"),
        interval: str = Query("1d"),  # Not currently used, but kept for future
        format: str = Query("html"),
        scaling: Optional[float] = Query(None)
):
    try:
        days = parse_period_to_days(period)
        df = load_yahoo_timeseries(ticker, exchange, days)
        effective_scaling = get_scaling_override(ticker, exchange, scaling)
        df = apply_scaling(df, effective_scaling)

        return handle_timeseries_response(df, format, f"Yahoo Time Series for {ticker}",
                                          f"{period} / {interval} (×{scaling})")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/timeseries/stooq", response_class=HTMLResponse)
def get_stooq_timeseries(
        ticker: str = Query(...),
        exchange: str = Query("L"),
        period: str = Query("1y"),
        interval: str = Query("1d"),
        format: str = Query("html"),
        scaling: Optional[float] = Query(None)
):
    try:
        days = parse_period_to_days(period)
        df = load_stooq_timeseries(ticker, exchange, days)
        effective_scaling = get_scaling_override(ticker, exchange,  scaling)
        df = apply_scaling(df, effective_scaling)

        return handle_timeseries_response(df, format, f"Stooq Time Series for {ticker}",
                                          f"{period} / {interval} (×{scaling})")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)

@app.get("/timeseries/meta", response_class=HTMLResponse)
def get_meta_timeseries(
        ticker: str = Query(...),
        exchange: str = Query("L"),
        period: str = Query("1y"),
        interval: str = Query("1d"),
        format: str = Query("html"),
        scaling: Optional[float] = Query(None)
):
    try:
        days = parse_period_to_days(period)
        df = load_meta_timeseries(ticker, exchange, days)
        effective_scaling = get_scaling_override(ticker, exchange, scaling)
        df = apply_scaling(df, effective_scaling)
        return handle_timeseries_response(df, format, f"Meta Time Series for {ticker}",
                                          f"{period} / {interval} (×{scaling})")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)
