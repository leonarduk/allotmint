# backend/routes/instrument_admin.py
from __future__ import annotations

"""Admin endpoints for managing instrument metadata."""

from typing import Any

from fastapi import APIRouter, HTTPException
from backend.config import config
from backend.common import instrument_groups
from backend.common.instruments import (
    _ORIGINAL_FETCH_METADATA,
    _fetch_metadata_from_yahoo,
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


@router.get("/admin/groups")
async def list_group_labels() -> list[str]:
    """Return known grouping labels from metadata and the persisted catalogue."""

    stored = set(instrument_groups.load_groups())
    for entry in list_instruments():
        value = entry.get("grouping")
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                stored.add(trimmed)
    return sorted(stored, key=str.casefold)


@router.post("/admin/groups")
async def create_group(body: dict[str, Any]) -> dict[str, Any]:
    """Persist a new grouping label if it does not already exist."""

    name = body.get("name")
    if not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name must be a string")
    existing = instrument_groups.load_groups()
    try:
        groups = instrument_groups.add_group(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    key = name.strip().casefold()
    canonical = next((g for g in groups if g.casefold() == key), name.strip())
    existed = any(g.casefold() == key for g in existing)
    status = "exists" if existed else "created"
    return {"status": status, "group": canonical, "groups": groups}

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
    meta = _load_meta_for_update(exchange, ticker)
    canonical_ticker = f"{ticker}.{exchange}"
    if "ticker" in body and body["ticker"] != canonical_ticker:
        raise HTTPException(status_code=400, detail="Ticker mismatch")
    if "exchange" in body and body["exchange"] != exchange:
        raise HTTPException(status_code=400, detail="Exchange mismatch")

    for key, value in body.items():
        if key in {"ticker", "exchange"}:
            continue
        meta[key] = value

    meta["ticker"] = canonical_ticker
    meta["exchange"] = exchange
    save_instrument_meta(ticker, exchange, meta)
    return {"status": "updated"}


@router.post("/admin/{exchange}/{ticker}/refresh")
async def refresh_instrument(
    exchange: str, ticker: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Fetch fresh metadata for an instrument and optionally persist it."""

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

    if (
        config.offline_mode
        and _fetch_metadata_from_yahoo is _ORIGINAL_FETCH_METADATA
    ):
        raise HTTPException(status_code=503, detail="Metadata refresh disabled in offline mode")

    preview = True
    if body is not None and isinstance(body, dict):
        preview = bool(body.get("preview", True))

    canonical_ticker = f"{ticker}.{exchange}"
    existing = _load_meta_for_update(exchange, ticker)

    fetched = _fetch_metadata_from_yahoo(canonical_ticker)
    if not fetched:
        raise HTTPException(status_code=502, detail="Unable to fetch instrument metadata")

    merged = dict(existing)
    changes: dict[str, dict[str, Any]] = {}
    for key, value in fetched.items():
        if key in {"ticker", "exchange"}:
            continue
        current = existing.get(key)
        if current != value:
            changes[key] = {"from": current, "to": value}
        merged[key] = value
        if key == "instrument_type":
            merged["instrumentType"] = value
        elif key == "instrumentType":
            merged["instrument_type"] = value

    if "instrument_type" in merged and "instrumentType" not in merged:
        merged["instrumentType"] = merged["instrument_type"]
    if "instrumentType" in merged and "instrument_type" not in merged:
        merged["instrument_type"] = merged["instrumentType"]

    merged["ticker"] = canonical_ticker
    merged["exchange"] = exchange

    if not preview:
        save_instrument_meta(ticker, exchange, merged)
        status = "updated"
    else:
        status = "preview"

    return {"status": status, "metadata": merged, "changes": changes}


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
        return {"status": "absent"}
    delete_instrument_meta(ticker, exchange)
    return {"status": "deleted"}


def _normalise_group(value: Any) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="group must be a string")
    group = value.strip()
    if not group:
        raise HTTPException(status_code=400, detail="group name must be provided")
    return group


def _load_meta_for_update(exchange: str, ticker: str) -> dict[str, Any]:
    existing = dict(get_instrument_meta(f"{ticker}.{exchange}") or {})
    existing.setdefault("ticker", f"{ticker}.{exchange}")
    existing.setdefault("exchange", exchange)
    return existing


@router.post("/admin/{exchange}/{ticker}/group")
async def assign_group(exchange: str, ticker: str, body: dict[str, Any]) -> dict[str, Any]:
    """Assign a grouping label to an instrument."""

    try:
        instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    group = _normalise_group(body.get("group"))
    meta = _load_meta_for_update(exchange, ticker)
    meta["grouping"] = group
    save_instrument_meta(ticker, exchange, meta)
    groups = instrument_groups.add_group(group)
    return {"status": "assigned", "group": group, "groups": groups}


@router.delete("/admin/{exchange}/{ticker}/group")
async def clear_group(exchange: str, ticker: str) -> dict[str, Any]:
    """Remove any grouping label assigned to an instrument."""

    try:
        instrument_meta_path(ticker, exchange)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = _load_meta_for_update(exchange, ticker)
    changed = False
    if "grouping" in meta:
        meta.pop("grouping", None)
        changed = True
    if changed:
        save_instrument_meta(ticker, exchange, meta)
    return {"status": "cleared"}

