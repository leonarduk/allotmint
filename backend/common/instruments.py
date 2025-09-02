"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

_INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"

METADATA_BUCKET_ENV = "METADATA_BUCKET"
METADATA_PREFIX_ENV = "METADATA_PREFIX"

logger = logging.getLogger(__name__)


def _s3_location() -> tuple[str, str] | None:
    bucket = os.getenv(METADATA_BUCKET_ENV)
    if not bucket:
        return None
    prefix = os.getenv(METADATA_PREFIX_ENV, "instruments").strip("/")
    if prefix:
        prefix += "/"
    return bucket, prefix


def _instrument_path(ticker: str) -> Path:
    sym, exch = (ticker.split(".", 1) + [None])[:2]
    sym = sym.upper()
    if sym == "CASH":
        ccy = (exch or "GBP").upper()
        return _INSTRUMENTS_DIR / "Cash" / f"{ccy}.json"
    folder = exch.upper() if exch else "Unknown"
    return _INSTRUMENTS_DIR / folder / f"{sym}.json"


def _instrument_key(ticker: str, prefix: str) -> str:
    rel = _instrument_path(ticker).relative_to(_INSTRUMENTS_DIR).as_posix()
    return f"{prefix}{rel}"


@lru_cache(maxsize=2048)
def get_instrument_meta(ticker: str) -> Dict[str, Any]:
    """Return metadata for ``ticker`` from disk or S3.

    The data files live under ``data/instruments`` or the configured S3
    location; failures return an empty dict.
    """
    path = _instrument_path(ticker)
    s3_loc = _s3_location()
    if s3_loc:
        bucket, prefix = s3_loc
        key = _instrument_key(ticker, prefix)
        try:
            import boto3  # type: ignore

            obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
            return json.loads(obj["Body"].read())
        except Exception as exc:
            logger.warning(
                "S3 load failed for %s/%s: %s; falling back to local file",
                bucket,
                key,
                exc,
            )
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid instrument JSON %s: %s", path, exc)
        return {}
    except Exception:
        logger.exception("Unexpected error loading instrument metadata for %s", path)
        raise


def save_instrument_meta(ticker: str, data: Dict[str, Any]) -> None:
    """Persist metadata locally and upload to S3 when configured."""
    path = _instrument_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    s3_loc = _s3_location()
    if s3_loc:
        bucket, prefix = s3_loc
        key = _instrument_key(ticker, prefix)
        try:
            import boto3  # type: ignore

            body = json.dumps(data).encode("utf-8")
            boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body)
        except Exception as exc:
            logger.warning(
                "Failed to upload instrument metadata for %s to s3://%s/%s: %s",
                ticker,
                bucket,
                key,
                exc,
            )
    get_instrument_meta.cache_clear()
