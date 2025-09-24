"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
import re
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

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

_AUTO_CREATE_FAILURES: set[str] = set()


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
        created = _auto_create_instrument_meta(ticker)
        return created or {}
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


def _clean_str(value: Any, *, upper: bool = False) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    if not text:
        return None
    return text.upper() if upper else text


def _asset_class_from_quote_type(quote_type: Optional[str]) -> Optional[str]:
    if not quote_type:
        return None
    mapping = {
        "EQUITY": "Equity",
        "ETF": "Fund",
        "MUTUALFUND": "Fund",
        "INDEX": "Index",
        "CURRENCY": "Currency",
        "CRYPTOCURRENCY": "Crypto",
        "FUTURE": "Derivative",
        "OPTION": "Derivative",
        "BOND": "Bond",
        "MONEYMARKET": "Cash",
    }
    key = quote_type.upper()
    if key in mapping:
        return mapping[key]
    return quote_type.replace("_", " ").title()


def _fetch_metadata_from_yahoo(full_ticker: str) -> Optional[Dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency missing
        logger.debug("yfinance unavailable; cannot fetch metadata for %s: %s", full_ticker, exc)
        return None

    try:
        stock = yf.Ticker(full_ticker)
    except Exception as exc:  # pragma: no cover - network/IO errors
        logger.warning("Failed to initialise yfinance for %s: %s", full_ticker, exc)
        return None

    info: Dict[str, Any] = {}
    try:
        fetched = stock.get_info()
        if isinstance(fetched, dict):
            info = fetched
    except Exception as exc:  # pragma: no cover - best effort fallback
        logger.debug("yfinance get_info failed for %s: %s", full_ticker, exc)
        try:
            fetched_attr = getattr(stock, "info", None)
            if isinstance(fetched_attr, dict):
                info = fetched_attr
        except Exception as exc_attr:  # pragma: no cover - best effort fallback
            logger.debug("yfinance info attribute failed for %s: %s", full_ticker, exc_attr)

    name = _clean_str(
        info.get("shortName")
        or info.get("longName")
        or info.get("displayName")
        or info.get("name")
        or full_ticker,
    )

    currency = _clean_str(info.get("currency"), upper=True)
    if not currency:
        try:
            fast = getattr(stock, "fast_info", None)
            if fast is not None:
                if isinstance(fast, dict):
                    currency = _clean_str(fast.get("currency"), upper=True)
                else:
                    currency = _clean_str(getattr(fast, "currency", None), upper=True)
        except Exception:  # pragma: no cover - best effort fallback
            currency = None

    sector = _clean_str(info.get("sector") or info.get("category"))
    industry = _clean_str(info.get("industry") or info.get("industryDisp"))
    region = _clean_str(info.get("region") or info.get("country") or info.get("market"))
    quote_type = _clean_str(info.get("quoteType"), upper=True)
    asset_class = _asset_class_from_quote_type(quote_type) if quote_type else None

    metadata: Dict[str, Any] = {
        "name": name or full_ticker,
        "currency": currency,
        "sector": sector,
        "region": region,
        "asset_class": asset_class,
        "industry": industry,
    }
    if quote_type:
        metadata["instrument_type"] = quote_type

    return {k: v for k, v in metadata.items() if v is not None}


_ORIGINAL_FETCH_METADATA = _fetch_metadata_from_yahoo


def _auto_create_instrument_meta(ticker: str) -> Optional[Dict[str, Any]]:
    canonical = (ticker or "").strip().upper()
    if not canonical or canonical in _AUTO_CREATE_FAILURES:
        return None

    sym, exch = (canonical.split(".", 1) + [None])[:2]
    if not exch or not sym or sym == "CASH":
        return None

    # Avoid triggering live lookups when the application is running in offline
    # mode.  Tests exercise the auto-create behaviour by monkeypatching
    # ``_fetch_metadata_from_yahoo``; allow those callers through even when the
    # real configuration is offline by checking that the helper has been
    # replaced.
    if config.offline_mode and _fetch_metadata_from_yahoo is _ORIGINAL_FETCH_METADATA:
        return None

    full = f"{sym}.{exch}"
    fetched = _fetch_metadata_from_yahoo(full)
    if not fetched:
        _AUTO_CREATE_FAILURES.add(full)
        return None

    payload: Dict[str, Any] = {
        "ticker": full,
        "exchange": exch,
        **fetched,
    }

    try:
        save_instrument_meta(sym, exch, payload)
    except Exception as exc:  # pragma: no cover - filesystem errors are rare
        logger.warning("Failed to persist auto-created metadata for %s: %s", full, exc)
    else:
        logger.info("Auto-created instrument metadata for %s from Yahoo Finance", full)

    return payload


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

