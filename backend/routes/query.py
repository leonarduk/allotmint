from __future__ import annotations

"""Custom query routes for analytics and saved queries.

Supported metrics:

* ``var`` – 1‑day Value at Risk using historical returns.
* ``meta`` – basic security metadata sourced from portfolios.
* ``price`` – time‑series of close prices between ``start`` and ``end``.
* ``position`` – aggregated position sizes per owner for each ticker.

``price`` can be resampled using the ``granularity`` field on ``CustomQuery``
(``daily``/``weekly``/``monthly``).
"""

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import compute_var, get_security_meta
from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/custom-query", tags=["query"])

QUERIES_DIR = Path("data/queries")


class CustomQuery(BaseModel):
    start: date
    end: date
    owners: Optional[List[str]] = None
    tickers: Optional[List[str]] = None
    metrics: List[str] = Field(default_factory=list)
    granularity: Optional[str] = Field(
        "daily", pattern="^(daily|weekly|monthly)$"
    )
    name: Optional[str] = None
    format: Optional[str] = Field("json", pattern="^(json|csv|xlsx)$")

    @model_validator(mode="after")
    def _check_targets(self):
        if not self.owners and not self.tickers:
            raise ValueError("owners or tickers must be supplied")
        return self


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _resolve_tickers(q: CustomQuery) -> List[str]:
    tickers: set[str] = set()
    if q.tickers:
        tickers.update(t.upper() for t in q.tickers)
    if q.owners:
        owners = {o.lower() for o in q.owners}
        for pf in list_portfolios():
            if pf.get("owner", "").lower() not in owners:
                continue
            for acct in pf.get("accounts", []):
                for h in acct.get("holdings", []):
                    t = (h.get("ticker") or "").upper()
                    if t:
                        tickers.add(t)
    return sorted(tickers)


def _close_column(df: pd.DataFrame) -> str | None:
    """Return the column name that holds close prices, case-insensitive."""
    mapping = {c.lower(): c for c in df.columns}
    return mapping.get("close") or mapping.get("adj close") or mapping.get("adj_close")


def _positions_for_ticker(ticker: str, owners: Optional[List[str]]) -> List[dict]:
    """Aggregate position units for ``ticker`` grouped by owner."""
    wanted = {o.lower() for o in owners} if owners else None
    rows: List[dict] = []
    for pf in list_portfolios():
        owner = (pf.get("owner") or "").lower()
        if wanted and owner not in wanted:
            continue
        total = 0.0
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                t = (h.get("ticker") or "").upper()
                if t == ticker or t.split(".", 1)[0] == ticker.split(".", 1)[0]:
                    total += float(h.get("units") or 0.0)
        if total:
            rows.append({"owner": pf.get("owner"), "units": total})
    return rows


@router.post("/run")
async def run_query(q: CustomQuery):
    tickers = _resolve_tickers(q)
    if not tickers:
        raise HTTPException(400, "No tickers found for query")

    rows = []
    for t in tickers:
        sym, exch = (t.split(".", 1) + ["L"])[:2]
        df = load_meta_timeseries_range(
            sym, exch, start_date=q.start, end_date=q.end
        )
        row = {"ticker": t}
        if "var" in q.metrics:
            row["var"] = compute_var(df)
        if "meta" in q.metrics:
            meta = get_security_meta(t) or {}
            row.update(meta)
        if "price" in q.metrics:
            col = _close_column(df) or "Close"
            if col in df.columns:
                df_px = df[[col]].copy()
                df_px.index = pd.to_datetime(df_px.index)
                freq_map = {"daily": "D", "weekly": "W", "monthly": "M"}
                if q.granularity in freq_map:
                    df_px = df_px.resample(freq_map[q.granularity]).last()
                row["price"] = [
                    {"date": idx.date().isoformat(), "close": float(val)}
                    for idx, val in df_px[col].items()
                ]
        if "position" in q.metrics:
            row["position"] = _positions_for_ticker(t, q.owners)
        rows.append(row)

    if q.name:
        slug = _slugify(q.name)
        QUERIES_DIR.mkdir(parents=True, exist_ok=True)
        (QUERIES_DIR / f"{slug}.json").write_text(json.dumps(q.model_dump(), default=str))

    if q.format == "csv":
        df = pd.DataFrame(rows)
        return PlainTextResponse(df.to_csv(index=False), media_type="text/csv")
    if q.format == "xlsx":
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return {"results": rows}


@router.get("/saved")
async def list_saved_queries():
    if not QUERIES_DIR.exists():
        return []
    return sorted(p.stem for p in QUERIES_DIR.glob("*.json"))


@router.get("/{slug}")
async def load_query(slug: str):
    path = QUERIES_DIR / f"{slug}.json"
    if not path.exists():
        raise HTTPException(404, "Query not found")
    return json.loads(path.read_text())


@router.post("/{slug}")
async def save_query(slug: str, q: CustomQuery):
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    path = QUERIES_DIR / f"{slug}.json"
    path.write_text(json.dumps(q.model_dump(), default=str))
    return {"saved": slug}
