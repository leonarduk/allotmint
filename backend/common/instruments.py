"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
import re
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from backend.config import config

logger = logging.getLogger(__name__)


def _resolve_instruments_dir() -> Path:
    """Return the configured instruments directory or fall back to bundled data."""

    configured_dir = config.data_root / "instruments"
    if configured_dir.is_dir():
        return configured_dir

    fallback_dir = Path(__file__).resolve().parents[2] / "data" / "instruments"
    if fallback_dir.is_dir():
        logger.warning(
            "Configured instruments directory %s missing; falling back to %s", configured_dir, fallback_dir
        )
        return fallback_dir

    logger.warning(
        "Configured instruments directory %s missing and fallback %s not found", configured_dir, fallback_dir
    )
    return configured_dir


_INSTRUMENTS_DIR = _resolve_instruments_dir()
_VALID_RE = re.compile(r"^[A-Z0-9-]+$")

METADATA_BUCKET_ENV = "METADATA_BUCKET"
METADATA_PREFIX_ENV = "METADATA_PREFIX"


@lru_cache(maxsize=1)
def list_group_definitions() -> Dict[str, Dict[str, Any]]:
    """Return catalogue of shared instrument group definitions."""

    root = config.data_root / "instruments" / "groupings"
    try:
        if not root.is_dir():
            return {}
    except OSError:
        return {}

    definitions: Dict[str, Dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            continue
        except Exception as exc:  # pragma: no cover - logged for visibility
            logger.warning("Failed to load group definition %s: %s", path, exc)
            continue

        if not isinstance(payload, dict):
            logger.warning("Group definition %s is not a JSON object", path)
            continue

        raw_id = payload.get("id")
        ident = str(raw_id if raw_id is not None else path.stem).strip()
        if not ident:
            ident = path.stem

        raw_name = payload.get("name")
        name = str(raw_name if raw_name is not None else ident).strip() or ident

        normalized = dict(payload)
        normalized["id"] = ident
        normalized["name"] = name
        definitions[ident] = normalized

    return definitions


def _validate_part(value: str) -> str:
    """Return ``value`` upper-cased if it matches ``_VALID_RE``."""

    value = value.upper()
    if not _VALID_RE.match(value):
        raise ValueError("invalid ticker or exchange")
    return value

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
    sym = _validate_part(sym)
    if exch is not None:
        exch = _validate_part(exch)
    if sym == "CASH":
        ccy = exch or "GBP"
        return _INSTRUMENTS_DIR / "Cash" / f"{ccy}.json"
    folder = exch if exch else "Unknown"
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
        path = _instrument_path(ticker)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid instrument JSON %s: %s", path, exc)
        return {}
    except ValueError:
        logger.warning("Invalid ticker format: %s", ticker)
        return {}
    except Exception:
        logger.exception("Unexpected error loading instrument metadata for %s", ticker)
        raise


def instrument_meta_path(ticker: str, exchange: str) -> Path:
    """Return the filesystem path for a ticker/exchange pair."""

    sym = _validate_part(ticker)
    exch = _validate_part(exchange)
    return _instrument_path(f"{sym}.{exch}")


def save_instrument_meta(
    ticker: str,
    exchange: str | Dict[str, Any],
    data: Optional[Dict[str, Any]] = None,
) -> Path:
    """Persist metadata for an instrument and optionally upload to S3.

    Supports calling as ``save_instrument_meta("ABC", "L", {...})`` or
    ``save_instrument_meta("ABC.L", {...})``.
    """

    if data is None:
        # called with composite ticker and data
        data = exchange  # type: ignore[assignment]
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        if "." not in ticker:
            raise ValueError("ticker must include exchange when data is second arg")
        ticker, exchange = ticker.split(".", 1)
    else:
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")

    path = instrument_meta_path(ticker, exchange)  # type: ignore[arg-type]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:  # pragma: no cover - filesystem errors are rare
        logger.exception("Failed to write instrument metadata %s", path)
        raise

    s3_loc = _s3_location()
    if s3_loc:
        bucket, prefix = s3_loc
        key = _instrument_key(f"{ticker}.{exchange}", prefix)
        try:
            import boto3  # type: ignore

            body = json.dumps(data).encode("utf-8")
            boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(
                "Failed to upload instrument metadata for %s.%s to s3://%s/%s: %s",
                ticker,
                exchange,
                bucket,
                key,
                exc,
            )

    get_instrument_meta.cache_clear()
    return path


def delete_instrument_meta(ticker: str, exchange: str) -> None:
    """Delete the metadata file for ``ticker`` on ``exchange`` if present."""

    path = instrument_meta_path(ticker, exchange)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        logger.warning("Permission denied deleting %s", path)
        return
    get_instrument_meta.cache_clear()

# def save_instrument_meta(ticker: str, meta: Dict[str, Any]) -> None:
#     """Write ``meta`` for ``ticker`` back to disk.

#     ``meta`` must already include ``ticker`` and any desired optional fields.
#     Missing directories are created automatically.
#     """

#     path = _instrument_path(ticker)
#     path.parent.mkdir(parents=True, exist_ok=True)
#     with path.open("w", encoding="utf-8") as f:
#         json.dump(meta, f, indent=2)


def list_instruments() -> List[Dict[str, Any]]:
    """Return metadata for every instrument found under ``data/instruments``."""

    instruments: List[Dict[str, Any]] = []
    for p in _INSTRUMENTS_DIR.rglob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for field in ("asset_class", "industry", "region", "grouping"):
                data.setdefault(field, None)
            instruments.append(data)
        except Exception:
            logger.warning("Failed to load instrument metadata for %s", p)
    return instruments

