"""
Local development API for AllotMint.

Run:
    uvicorn backend.local_api.main:app --reload

This serves JSON from ./data-sample/... for frontend development.
"""

from fastapi import FastAPI, HTTPException
from backend.common.data_loader import load_account, list_plots
import os

app = FastAPI(title="AllotMint Local API", version="0.1")

# Force local mode (override env)
os.environ.setdefault("ALLOTMINT_ENV", "local")


@app.get("/health")
def health():
    return {"status": "ok", "env": os.getenv("ALLOTMINT_ENV", "local")}


@app.get("/owners")
def owners():
    # list owners + available accounts
    return list_plots()


@app.get("/account/{owner}/{account}")
def get_account(owner: str, account: str):
    try:
        return load_account(owner, account)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
