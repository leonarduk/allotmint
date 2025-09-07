from __future__ import annotations

"""Custom query routes for analytics and saved queries."""

import io
import json
import os
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
from backend.config import config
from backend.timeseries.cache import load_meta_timeseries_range

router = APIRouter(prefix="/custom-query", tags=["query"])

QUERIES_DIR = config.data_root / "queries"
DATA_BUCKET_ENV = "DATA_BUCKET"
QUERIES_PREFIX = "queries/"


class CustomQuery(BaseModel):
    start: date
    end: date
    owners: Optional[List[str]] = None
    tickers: Optional[List[str]] = None
    metrics: List[str] = Field(default_factory=list)
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


def _save_query_local(slug: str, q: CustomQuery) -> None:
    """Persist a query to the local filesystem."""
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    (QUERIES_DIR / f"{slug}.json").write_text(json.dumps(q.model_dump(), default=str))


def _save_query_s3(slug: str, q: CustomQuery) -> None:
    """Persist a query to S3 under ``queries/<slug>.json``."""
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        raise HTTPException(500, "Missing DATA_BUCKET env var for AWS query saving")
    try:
        import boto3  # type: ignore

        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=f"{QUERIES_PREFIX}{slug}.json",
            Body=json.dumps(q.model_dump(), default=str).encode("utf-8"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(500, f"Failed to write query to S3: {exc}")


def _list_queries_s3() -> List[str]:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        return []
    try:
        import boto3  # type: ignore

        s3 = boto3.client("s3")
    except Exception:  # pragma: no cover - defensive
        return []

    slugs: set[str] = set()
    token: str | None = None
    while True:
        params = {"Bucket": bucket, "Prefix": QUERIES_PREFIX}
        if token:
            params["ContinuationToken"] = token
        resp = s3.list_objects_v2(**params)
        for item in resp.get("Contents", []):
            key = item.get("Key", "")
            if key.endswith(".json") and key.startswith(QUERIES_PREFIX):
                slugs.add(Path(key).stem)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(slugs)


def _load_query_s3(slug: str) -> dict:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        raise HTTPException(404, "Query not found")
    try:
        import boto3  # type: ignore

        obj = boto3.client("s3").get_object(
            Bucket=bucket, Key=f"{QUERIES_PREFIX}{slug}.json"
        )
        body = obj.get("Body")
        txt = body.read().decode("utf-8") if body else ""
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(404, "Query not found") from exc
    if not txt:
        raise HTTPException(404, "Query not found")
    return json.loads(txt)


@router.post("/run")
async def run_query(q: CustomQuery):
    tickers = _resolve_tickers(q)
    if not tickers:
        raise HTTPException(400, "No tickers found for query")

    rows = []
    for t in tickers:
        sym, exch = (t.split(".", 1) + ["L"])[:2]
        df = load_meta_timeseries_range(sym, exch, start_date=q.start, end_date=q.end)
        row = {"ticker": t}
        if "var" in q.metrics:
            row["var"] = compute_var(df)
        if "meta" in q.metrics:
            meta = get_security_meta(t) or {}
            row.update(meta)
        rows.append(row)

    if q.name:
        slug = _slugify(q.name)
        if config.app_env == "aws":
            _save_query_s3(slug, q)
        else:
            _save_query_local(slug, q)

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
    if config.app_env == "aws":
        return _list_queries_s3()
    if not QUERIES_DIR.exists():
        return []
    return sorted(p.stem for p in QUERIES_DIR.glob("*.json"))


@router.get("/{slug}")
async def load_query(slug: str):
    if config.app_env == "aws":
        return _load_query_s3(slug)
    path = QUERIES_DIR / f"{slug}.json"
    if not path.exists():
        raise HTTPException(404, "Query not found")
    return json.loads(path.read_text())


@router.post("/{slug}")
async def save_query(slug: str, q: CustomQuery):
    if config.app_env == "aws":
        _save_query_s3(slug, q)
        return {"saved": slug}
    QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    path = QUERIES_DIR / f"{slug}.json"
    path.write_text(json.dumps(q.model_dump(), default=str))
    return {"saved": slug}
