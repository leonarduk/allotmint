from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ModuleNotFoundError:  # pragma: no cover - exercised in tests when missing
    letter = None
    canvas = None

from backend.common import portfolio_utils
from backend.config import config

logger = logging.getLogger(__name__)


@dataclass
class ReportData:
    owner: str
    start: Optional[date]
    end: Optional[date]
    realized_gains_gbp: float
    income_gbp: float
    cumulative_return: Optional[float]
    max_drawdown: Optional[float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "owner": self.owner,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "realized_gains_gbp": round(self.realized_gains_gbp, 2),
            "income_gbp": round(self.income_gbp, 2),
            "cumulative_return": self.cumulative_return,
            "max_drawdown": self.max_drawdown,
        }


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _transaction_roots() -> Iterable[str]:
    if config.app_env == "aws":
        yield "transactions"
        return
    roots: List[str] = []
    if config.transactions_output_root:
        roots.append(str(config.transactions_output_root))
    if config.accounts_root:
        roots.append(str(config.accounts_root))
    roots.append(str(config.data_root / "transactions"))
    seen = set()
    for r in roots:
        path = Path(r)
        if r not in seen and path.exists():
            seen.add(r)
            yield r


def _load_transactions(owner: str) -> List[dict]:
    records: List[dict] = []
    if config.app_env == "aws":
        bucket = os.getenv("DATA_BUCKET")
        if not bucket:
            raise RuntimeError("DATA_BUCKET environment variable is required in AWS")
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime
            raise RuntimeError("boto3 is required for loading transactions from S3") from exc
        s3 = boto3.client("s3")
        for root in _transaction_roots():
            prefix = f"{root.rstrip('/')}/{owner}/"
            paginator = s3.get_paginator("list_objects_v2")
            try:
                pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
            except (BotoCoreError, ClientError) as exc:
                logger.warning("failed to paginate S3 objects for prefix %s: %s", prefix, exc)
                continue
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    if not key.endswith("_transactions.json"):
                        continue
                    try:
                        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                        data = json.loads(body)
                    except (BotoCoreError, ClientError, json.JSONDecodeError) as exc:
                        logger.warning("failed to load %s from bucket %s: %s", key, bucket, exc)
                        continue
                    txs = data.get("transactions") if isinstance(data, dict) else None
                    if isinstance(txs, list):
                        records.extend(txs)
        return records
    for root in _transaction_roots():
        owner_dir = Path(root) / owner
        if not owner_dir.exists():
            continue
        for path in owner_dir.glob("*_transactions.json"):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("failed to read %s: %s", path, exc)
                continue
            txs = data.get("transactions") if isinstance(data, dict) else None
            if isinstance(txs, list):
                records.extend(txs)
    return records


def compile_report(owner: str, start: Optional[date] = None, end: Optional[date] = None) -> ReportData:
    txs = _load_transactions(owner)
    realized = 0.0
    income = 0.0
    for t in txs:
        try:
            d = datetime.fromisoformat(t.get("date")) if t.get("date") else None
        except Exception:
            d = None
        if start and d and d.date() < start:
            continue
        if end and d and d.date() > end:
            continue
        amount = float(t.get("amount_minor") or 0.0) / 100.0
        typ = (t.get("type") or "").upper()
        if typ == "SELL":
            realized += amount
        elif typ in {"DIVIDEND", "INTEREST"}:
            income += amount

    perf = portfolio_utils.compute_owner_performance(owner)
    hist = perf.get("history", [])
    if start or end:
        filtered: List[dict] = []
        for row in hist:
            try:
                d = datetime.fromisoformat(row["date"]).date()
            except Exception:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            filtered.append(row)
        hist = filtered
    cumulative = hist[-1]["cumulative_return"] if hist else None
    return ReportData(
        owner=owner,
        start=start,
        end=end,
        realized_gains_gbp=realized,
        income_gbp=income,
        cumulative_return=cumulative,
        max_drawdown=perf.get("max_drawdown"),
    )


def report_to_csv(data: ReportData) -> bytes:
    df = pd.DataFrame([data.to_dict()])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def report_to_pdf(data: ReportData) -> bytes:
    if canvas is None:
        raise RuntimeError("reportlab is required for PDF output")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    text = c.beginText(40, 750)
    for k, v in data.to_dict().items():
        text.textLine(f"{k}: {v}")
    c.drawText(text)
    c.showPage()
    c.save()
    return buf.getvalue()

