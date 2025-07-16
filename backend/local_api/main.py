from fastapi import FastAPI, HTTPException
import os

from backend.common.data_loader import list_plots, load_account
from backend.common.portfolio import build_owner_portfolio

app = FastAPI(title="AllotMint Local API", version="0.1")


os.environ.setdefault("ALLOTMINT_ENV", "local")


@app.get("/health")
def health():
    return {"status": "ok", "env": os.getenv("ALLOTMINT_ENV", "local")}


@app.get("/owners")
def owners():
    return list_plots()


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
