# backend/routes/instrument_admin.py
from __future__ import annotations

"""Admin endpoints for managing instrument metadata."""

from typing import Any

from fastapi import APIRouter, HTTPException
from backend.common.instruments import (
    delete_instrument_meta,
    get_instrument_meta,
    instrument_meta_path,
    list_group_definitions,
    save_instrument_meta,
    list_instruments,
)

router = APIRouter(
    prefix="/instrument",
    tags=["instrument"],
)


@router.get("/admin")
async def list_instrument_metadata() -> list[dict[str, Any]]:
    """Return metadata for all instruments."""

    return list_instruments()


@router.get("/admin/groupings")
async def list_instrument_groupings() -> list[dict[str, Any]]:
    """Return shared instrument grouping definitions."""

    catalogue = list_group_definitions()
    return sorted((dict(entry) for entry in catalogue.values()), key=lambda item: item.get("id", ""))


@router.get("/admin/{exchange}/{ticker}")
async def get_instrument(exchange: str, ticker: str) -> dict[str, Any]:
    """Return metadata for a ticker/exchange pair."""

    try:
        instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    meta = get_instrument_meta(f"{ticker}.{exchange}")
    if not meta:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return meta


@router.post("/admin/{exchange}/{ticker}")
async def create_instrument(exchange: str, ticker: str, body: dict[str, Any]) -> dict[str, str]:
    """Create metadata for a new instrument."""

    try:
        path = instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        exists = path.exists()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Filesystem error") from exc
    if exists:
        raise HTTPException(status_code=409, detail="Instrument already exists")
    if body.get("ticker") and body["ticker"] != f"{ticker}.{exchange}":
        raise HTTPException(status_code=400, detail="Ticker mismatch")
    save_instrument_meta(ticker, exchange, body)
    return {"status": "created"}


@router.put("/admin/{exchange}/{ticker}")
async def update_instrument(exchange: str, ticker: str, body: dict[str, Any]) -> dict[str, str]:
    """Update metadata for an existing instrument."""

    try:
        path = instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        exists = path.exists()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Filesystem error") from exc
    if not exists:
        raise HTTPException(status_code=404, detail="Instrument not found")
    if body.get("ticker") and body["ticker"] != f"{ticker}.{exchange}":
        raise HTTPException(status_code=400, detail="Ticker mismatch")
    save_instrument_meta(ticker, exchange, body)
    return {"status": "updated"}


@router.delete("/admin/{exchange}/{ticker}")
async def delete_instrument(exchange: str, ticker: str) -> dict[str, str]:
    """Remove instrument metadata from disk."""

    try:
        path = instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        exists = path.exists()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Filesystem error") from exc
    if not exists:
        raise HTTPException(status_code=404, detail="Instrument not found")
    delete_instrument_meta(ticker, exchange)
    return {"status": "deleted"}

