from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware   # <-- add

import os
from backend.common.data_loader import list_plots, load_account
from backend.common.portfolio import build_owner_portfolio
from backend.common.group_portfolio import list_groups, build_group_portfolio
from backend.common.prices import refresh_prices

import logging

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

# add just once after other routes
from backend.common.portfolio_utils import aggregate_by_ticker

@app.get("/portfolio-group/{slug}/instruments")
def group_instruments(slug: str):
    """
    One row per ticker across the whole group, enriched with
    last price and % changes.
    """
    gp = build_group_portfolio(slug)
    return aggregate_by_ticker(gp)

from backend.common.instrument_api import timeseries_for_ticker, positions_for_ticker

@app.get("/portfolio-group/{slug}/instrument/{ticker}")
def instrument_detail(slug: str, ticker: str, days: int = 365):
    """
    JSON payload:
      {
        'prices': [ {date, close_gbp}, ... ],
        'positions': [ {owner, units, market_value_gbp, ...}, ... ]
      }
    """
    return {
        "prices": timeseries_for_ticker(ticker.upper(), days=days),
        "positions": positions_for_ticker(slug, ticker.upper()),
    }
