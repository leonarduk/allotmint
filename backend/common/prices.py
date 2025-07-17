from __future__ import annotations

"""
Price + FX caching for AllotMint.

- Reads securities.csv to know which tickers & currencies to load.
- Fetches latest price via yfinance.
- Fetches FX to GBP where needed.
- Writes cache (prices.json) locally or to S3.
- Provides get_price_gbp(ticker) for valuation.

NOTE: Minimal error handling for MVP.
"""

import csv
import json
import os
import pathlib
import time
from dataclasses import dataclass
from typing import Dict, Optional

import datetime as dt

import yfinance as yf  # install in backend/requirements.txt

# paths
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_UNIVERSE = _REPO_ROOT / "data-sample" / "universe"
_LOCAL_SECURITIES_CSV = _LOCAL_UNIVERSE / "securities.csv"
_LOCAL_PRICES_JSON = _LOCAL_UNIVERSE / "prices.json"

DATA_BUCKET_ENV = "DATA_BUCKET"
UNIVERSE_PREFIX = "universe/"  # in S3: universe/securities.csv, universe/prices.json


# ------------------------------------------------------------
# Data models
# ------------------------------------------------------------
@dataclass
class SecMeta:
    ticker: str
    name: str
    currency: str
    price_ticker: str
    px_scale: float = 1.0   # <-- NEW


# ------------------------------------------------------------
# Load securities metadata
# ------------------------------------------------------------
def load_securities_local() -> Dict[str, SecMeta]:
    """
    Load security metadata from data-sample/universe/securities.csv.

    Returns dict keyed by *your* internal ticker (the one used in holdings).

    CSV columns:
      ticker        (required)
      name          (optional)
      currency      (default GBP)
      price_ticker  (default ticker)
      px_scale      (default 1.0)  <-- use 0.01 if feed is GBp but you want GBP

    Any rows missing `ticker` are skipped.
    """
    out: Dict[str, SecMeta] = {}

    if not _LOCAL_SECURITIES_CSV.exists():
        return out

    with open(_LOCAL_SECURITIES_CSV, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            t_raw = (r.get("ticker") or "").strip()
            if not t_raw:
                continue  # skip blank row
            t = t_raw  # preserve case; tickers are case-sensitive in our map

            name = (r.get("name") or t).strip()

            currency = (r.get("currency") or "GBP").strip().upper()

            price_ticker = (r.get("price_ticker") or t).strip()

            # Parse px_scale; be forgiving (blank, None, bad string)
            px_scale_txt = r.get("px_scale")
            try:
                px_scale = float(px_scale_txt) if px_scale_txt not in (None, "", " ") else 1.0
            except Exception:  # noqa: BLE001
                px_scale = 1.0

            out[t] = SecMeta(
                ticker=t,
                name=name,
                currency=currency,
                price_ticker=price_ticker,
                px_scale=px_scale,
            )

    return out



def load_securities(env: Optional[str] = None) -> Dict[str, SecMeta]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    if env == "aws":
        # TODO: load from S3 (later); fall back to local now
        pass
    return load_securities_local()


# ------------------------------------------------------------
# FX support
# ------------------------------------------------------------
# Map currency->(fx_ticker, invert) where fx_ticker returns units_of_other per GBP
FX_MAP = {
    "USD": ("GBPUSD=X", True),  # GBPUSD = USD per GBP; we want GBP = USD / quote
    "EUR": ("GBPEUR=X", True),
    "GBP": (None, False),
}

def fetch_fx_to_gbp(currency: str) -> float:
    currency = currency.upper()
    if currency == "GBP":
        return 1.0
    fx_meta = FX_MAP.get(currency)
    if not fx_meta:
        raise ValueError(f"No FX mapping for {currency}")
    fx_ticker, invert = fx_meta
    data = yf.Ticker(fx_ticker).fast_info  # fast_info has last_price
    quote = float(data["last_price"])
    return 1.0 / quote if invert else quote


# ------------------------------------------------------------
# Price fetch & cache
# ------------------------------------------------------------
def fetch_price_native(price_ticker: str) -> float:
    tk = yf.Ticker(price_ticker)
    fi = tk.fast_info
    return float(fi["last_price"])


def build_price_cache(env: Optional[str] = None) -> Dict[str, Dict]:
    """
    Return dict keyed by internal ticker.
    {
      "VUSA.L": {
        "price_native": 543.21,
        "currency": "USD",
        "fx_to_gbp": 0.77,
        "price_gbp": 417.27,
        "timestamp": "2025-07-16T21:59:00Z"
      },
      ...
    }
    """
    secs = load_securities(env=env)
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    cache: Dict[str, Dict] = {}
    # prefetch FX used
    fx_cache: Dict[str, float] = {}
    for s in secs.values():
        fx_cache.setdefault(s.currency, fetch_fx_to_gbp(s.currency))

    for s in secs.values():
        try:
            p_native_raw = fetch_price_native(s.price_ticker)
            p_native = p_native_raw * s.px_scale  # scale to stated currency units
        except Exception:
            p_native = None
        fx = fx_cache.get(s.currency, 1.0)
        p_gbp = p_native * fx if p_native is not None else None
        cache[s.ticker] = {
            "currency": s.currency,
            "price_native": p_native,
            "fx_to_gbp": fx,
            "price_gbp": p_gbp,
            "timestamp": now,
        }
    return cache


def save_price_cache_local(cache: Dict[str, Dict]) -> None:
    _LOCAL_PRICES_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCAL_PRICES_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def load_price_cache_local() -> Dict[str, Dict]:
    try:
        if not _LOCAL_PRICES_JSON.exists() or _LOCAL_PRICES_JSON.stat().st_size == 0:
            return {}
        with open(_LOCAL_PRICES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_price_gbp(ticker: str, env: Optional[str] = None, refresh: bool = False) -> Optional[float]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    cache = load_price_cache_local()

    if refresh or ticker not in cache:
        try:
            cache = build_price_cache(env=env)
            save_price_cache_local(cache)
        except Exception:
            pass  # swallow; fall through
        cache = load_price_cache_local()

    entry = cache.get(ticker)
    return entry.get("price_gbp") if entry else None

def refresh_prices(env: Optional[str] = None) -> Dict[str, Any]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    try:
        cache = build_price_cache(env=env)
        save_price_cache_local(cache)
    except Exception as exc:
        # fall back: load existing cache size
        try:
            cache = load_price_cache_local()
        except Exception:
            cache = {}
        return {"env": env, "tickers": len(cache), "timestamp": None, "error": str(exc)}
    return {
        "env": env,
        "tickers": len(cache),
        "timestamp": next(iter(cache.values()))["timestamp"] if cache else None,
    }
