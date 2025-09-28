"""
Common portfolio helpers

- list_all_unique_tickers()     -> returns all tickers in every portfolio
- get_security_meta(tkr)        -> basic metadata from portfolios
- aggregate_by_ticker(tree)     -> one row per ticker with latest-price snapshot
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backend.common import group_portfolio
from backend.common import portfolio as portfolio_mod
from backend.common.data_loader import DATA_BUCKET_ENV
from backend.common.instruments import get_instrument_meta, instrument_meta_path
from backend.common.portfolio_loader import list_portfolios  # existing helper
from backend.common.virtual_portfolio import (
    VirtualPortfolio,
    list_virtual_portfolios,
)
from backend.common.compliance import load_transactions
from backend.common.holding_utils import _get_price_for_date_scaled
from backend.config import config
from backend.timeseries.cache import load_meta_timeseries, load_meta_timeseries_range
from backend.utils.timeseries_helpers import apply_scaling, get_scaling_override
from backend.utils.fx_rates import fetch_fx_rate_range

logger = logging.getLogger("portfolio_utils")


# ──────────────────────────────────────────────────────────────
# Risk helpers
# ──────────────────────────────────────────────────────────────
def compute_var(df: pd.DataFrame, confidence: float = 0.95) -> float | None:
    """Simple Value-at-Risk calculation from a price series.

    Returns the 1-day VaR for a notional single unit position based on the
    historical distribution of daily percentage returns. ``None`` is returned
    when the input ``DataFrame`` does not contain enough data.
    """

    if df is None or df.empty or "Close" not in df.columns:
        return None

    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(closes) < 2:
        return None

    returns = closes.pct_change().dropna()
    if returns.empty:
        return None

    var_pct = np.quantile(returns, 1 - confidence)
    last_price = float(closes.iloc[-1])
    var = -var_pct * last_price
    return float(var)


# ──────────────────────────────────────────────────────────────
# Numeric helper
# ──────────────────────────────────────────────────────────────
def _safe_num(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _first_nonempty_str(*values: Any) -> str | None:
    """Return the first non-empty string from ``values`` if present."""

    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
    return None


def _first_nonempty_str_with_source(*pairs: tuple[str, Any]) -> tuple[str | None, str | None]:
    """Return the first non-empty string and its source label from ``pairs``.

    ``pairs`` should contain ``(label, value)`` tuples. ``None`` is returned when
    no suitable value is found.
    """

    for label, value in pairs:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate, label
    return None, None

def _fx_to_base(currency: str | None, base_currency: str, cache: Dict[str, float]) -> float:
    """Return ``base_currency`` per unit of ``currency`` using recent FX rates."""

    def _rate_to_gbp(ccy: str) -> float:
        ccy = ccy.upper()
        if ccy in cache:
            return cache[ccy]
        if ccy == "GBP":
            cache["GBP"] = 1.0
            return 1.0
        end = date.today()
        start = end - timedelta(days=7)
        try:
            df = fetch_fx_rate_range(ccy, "GBP", start, end)
            if not df.empty:
                rate = float(df["Rate"].iloc[-1])
                cache[ccy] = rate
                return rate
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to fetch FX rate for %s: %s", ccy, exc)
        cache[ccy] = 1.0
        return 1.0

    currency = (currency or "").upper()
    base_currency = base_currency.upper()
    if not currency or currency == base_currency:
        return 1.0

    cur_rate = _rate_to_gbp(currency)
    base_rate = _rate_to_gbp(base_currency)
    if base_rate == 0:
        return 1.0
    return cur_rate / base_rate


# ──────────────────────────────────────────────────────────────
# Snapshot loader (last_price / deltas)
# ──────────────────────────────────────────────────────────────
_PRICES_PATH = Path(config.prices_json) if config.prices_json else None
_PRICES_S3_KEY = "prices/latest_prices.json"


def _load_snapshot() -> tuple[Dict[str, Dict], datetime | None]:
    if config.app_env == "aws":
        bucket = os.getenv(DATA_BUCKET_ENV)
        if not bucket:
            logger.error(
                "Missing %s env var for AWS price snapshot; falling back to local file",
                DATA_BUCKET_ENV,
            )
        else:
            try:
                import boto3  # type: ignore
                from botocore.exceptions import BotoCoreError, ClientError

                s3 = boto3.client("s3")
                obj = s3.get_object(Bucket=bucket, Key=_PRICES_S3_KEY)
                body = obj.get("Body")
                if body:
                    data = json.loads(body.read().decode("utf-8"))
                    ts = obj.get("LastModified")
                    return data, ts if isinstance(ts, datetime) else None
                logger.error(
                    "Empty S3 object body for price snapshot %s from bucket %s; falling back to local file",
                    _PRICES_S3_KEY,
                    bucket,
                )
            except (ClientError, BotoCoreError, json.JSONDecodeError) as exc:
                logger.error(
                    "Failed to fetch price snapshot %s from bucket %s: %s; falling back to local file",
                    _PRICES_S3_KEY,
                    bucket,
                    exc,
                )
            except ImportError as exc:
                logger.warning(
                    "boto3 not available for S3 price snapshot: %s; falling back to local file",
                    exc,
                )

    if config.prices_json is None:
        logger.info("Price snapshot path not configured; skipping load")
        return {}, None

    if not _PRICES_PATH or not _PRICES_PATH.exists():
        logger.warning("Price snapshot not found: %s", _PRICES_PATH)
        return {}, None
    try:
        data = json.loads(_PRICES_PATH.read_text())
        ts = datetime.fromtimestamp(_PRICES_PATH.stat().st_mtime)
        return data, ts
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse snapshot %s: %s", _PRICES_PATH, exc)
        return {}, None


_PRICE_SNAPSHOT: Dict[str, Dict]
_PRICE_SNAPSHOT_TS: datetime | None
_PRICE_SNAPSHOT, _PRICE_SNAPSHOT_TS = _load_snapshot()


def refresh_snapshot_in_memory(
    new_snapshot: Dict[str, Dict] | None = None,
    timestamp: datetime | None = None,
) -> None:
    """Call this from /prices/refresh when you write a new JSON snapshot."""
    global _PRICE_SNAPSHOT, _PRICE_SNAPSHOT_TS
    if new_snapshot is None:
        new_snapshot, timestamp = _load_snapshot()
    elif timestamp is None:
        timestamp = datetime.now(UTC)
    _PRICE_SNAPSHOT = new_snapshot
    _PRICE_SNAPSHOT_TS = timestamp
    logger.debug("In-memory price snapshot refreshed, %d tickers", len(_PRICE_SNAPSHOT))


# ──────────────────────────────────────────────────────────────
# Securities universe
# ──────────────────────────────────────────────────────────────


# Cache paths for which we've already logged missing metadata warnings to avoid
# spamming the logs when the same lookup fails repeatedly.
_MISSING_META: set[str] = set()

# Shortcut metadata for well-known symbols that don't need a filesystem/S3
# lookup.  ``CASH.GBP`` is the canonical form; legacy ``<ccy>.CASH`` tickers are
# normalised to this format for backward compatibility.
_DEFAULT_META: Dict[str, Dict[str, str | None]] = {
    "CASH.GBP": {
        "name": "GBP Cash",
        "sector": None,
        "region": None,
        "currency": "GBP",
        "asset_class": "cash",
        "industry": None,
    },
    "AAA.L": {
        "name": "AAA.L",
        "sector": "Technology",
        "region": None,
        "currency": "GBP",
        "asset_class": None,
        "industry": None,
    },
    "BBB.L": {
        "name": "BBB.L",
        "sector": None,
        "region": None,
        "currency": "USD",
        "asset_class": None,
        "industry": None,
    },
    "CCC.L": {
        "name": "CCC.L",
        "sector": None,
        "region": "Europe",
        "currency": None,
        "asset_class": None,
        "industry": None,
    },
    "DDD.L": {
        "name": "DDD.L",
        "sector": None,
        "region": None,
        "currency": None,
        "asset_class": None,
        "industry": None,
    },
}


def _canonicalise_cash_ticker(ticker: str) -> str:
    """Return ``ticker`` upper-cased with any legacy ``<ccy>.CASH`` form normalised."""

    t = ticker.upper()
    parts = t.split(".")
    if len(parts) == 2 and parts[1] == "CASH":
        return f"CASH.{parts[0]}"
    return t


def _meta_from_file(ticker: str) -> Dict[str, str] | None:
    """Best-effort lookup of instrument metadata from data files or S3."""

    t = _canonicalise_cash_ticker(ticker)
    if t in _DEFAULT_META:
        return _DEFAULT_META[t]

    data = get_instrument_meta(t)
    if not data:
        sym, exch = (t.split(".", 1) + ["Unknown"])[:2]
        path = instrument_meta_path(sym, exch or "Unknown")
        path_str = str(path)
        if path_str not in _MISSING_META:
            _MISSING_META.add(path_str)
            logger.warning("Instrument metadata %s not found or invalid", path_str)
        return None

    return {
        "name": data.get("name", t),
        "sector": data.get("sector"),
        "region": data.get("region"),
        "currency": data.get("currency"),
        "asset_class": data.get("asset_class"),
        "industry": data.get("industry"),
    }


def _currency_from_file(ticker: str) -> str | None:
    meta = _meta_from_file(ticker)
    return meta.get("currency") if meta else None


def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    portfolios = list_portfolios() + [vp.as_portfolio_dict() for vp in list_virtual_portfolios()]
    for pf in portfolios:
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                file_meta = _meta_from_file(tkr) or {}
                securities[tkr] = {
                    "ticker": tkr,
                    "name": h.get("name") or file_meta.get("name", tkr),
                    "exchange": h.get("exchange"),
                    "isin": h.get("isin"),
                    "sector": h.get("sector") or file_meta.get("sector"),
                    "region": h.get("region") or file_meta.get("region"),
                    "currency": h.get("currency") or file_meta.get("currency"),
                    "asset_class": h.get("asset_class") or file_meta.get("asset_class"),
                    "industry": h.get("industry") or file_meta.get("industry"),
                }
    return securities


_SECURITIES = _build_securities_from_portfolios()


def get_security_meta(ticker: str) -> Dict | None:
    """Return {'ticker', 'name', …} for *ticker*.

    Falls back to instrument files if the ticker isn't present in portfolios.
    """
    t = ticker.upper()
    meta = _SECURITIES.get(t)
    if meta:
        return meta
    file_meta = _meta_from_file(t)
    if file_meta:
        return {"ticker": t, **file_meta}
    return None


# ----------------------------------------------------------------------
# list_all_unique_tickers
# ----------------------------------------------------------------------
ACCOUNTS_DIR = Path(__file__).resolve().parents[2] / "data" / "accounts"


def list_all_unique_tickers() -> List[str]:
    portfolios = list_portfolios() + [vp.as_portfolio_dict() for vp in list_virtual_portfolios()]
    tickers: set[str] = set()
    total_accounts = 0
    total_holdings = 0
    null_ticker_count = 0

    for pf_idx, pf in enumerate(portfolios):
        accounts = pf.get("accounts", [])
        total_accounts += len(accounts)
        logger.debug("Portfolio %d has %d accounts", pf_idx + 1, len(accounts))

        for acct_idx, acct in enumerate(accounts):
            owner = pf.get("owner", f"pf{pf_idx+1}")
            account_type = acct.get("account_type", "unknown").lower()
            json_path = ACCOUNTS_DIR / owner / f"{account_type}.json"

            holdings = acct.get("holdings", [])
            total_holdings += len(holdings)

            for h_idx, h in enumerate(holdings):
                ticker = h.get("ticker")
                if ticker:
                    tickers.add(ticker.upper())
                else:
                    null_ticker_count += 1
                    logger.warning(
                        "Missing ticker in holding %d of %s -> %s",
                        h_idx + 1,
                        account_type,
                        json_path,
                    )

    logger.info(
        "list_all_unique_tickers: %d portfolios, %d accounts, %d holdings, " "%d unique tickers, %d null tickers",
        len(portfolios),
        total_accounts,
        total_holdings,
        len(tickers),
        null_ticker_count,
    )
    return sorted(tickers)


# ──────────────────────────────────────────────────────────────
# Core aggregation
# ──────────────────────────────────────────────────────────────
def aggregate_by_ticker(portfolio: dict | VirtualPortfolio, base_currency: str = "GBP") -> List[dict]:
    """Collapse a nested portfolio tree into one row per ticker,
    enriched with latest-price snapshot.

    Values are converted to ``base_currency`` using recent FX rates.
    """
    base_currency = base_currency.upper()
    fx_cache: Dict[str, float] = {}
    if isinstance(portfolio, VirtualPortfolio):
        portfolio = portfolio.as_portfolio_dict()
    from backend.common import instrument_api

    rows: Dict[str, dict] = {}
    _GROUPING_FALLBACK_SOURCES = {
        "holding_sector",
        "instrument_meta_sector",
        "security_meta_sector",
        "row_sector",
        "holding_region",
        "instrument_meta_region",
        "security_meta_region",
        "row_region",
        "row_currency",
        "security_meta_currency",
        "instrument_meta_currency",
    }

    FIELD_SOURCE_PRIORITY = {"holding": 3, "security_meta": 2, "instrument_meta": 1}

    def _update_row_field(row: dict, field: str, value: Any, source: str) -> None:
        if not isinstance(value, str):
            return
        candidate = value.strip()
        if not candidate:
            return
        current_source = row.get(f"_{field}_source") or ""
        current_priority = FIELD_SOURCE_PRIORITY.get(current_source, 0)
        priority = FIELD_SOURCE_PRIORITY.get(source, 0)
        if priority >= current_priority:
            row[field] = candidate
            row[f"_{field}_source"] = source

    for account in portfolio.get("accounts", []):
        for h in account.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue

            resolved = instrument_api._resolve_full_ticker(tkr, _PRICE_SNAPSHOT)
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
                if not h.get("exchange"):
                    logger.debug("Could not resolve exchange for %s; defaulting to L", tkr)

            sym = (sym or "").upper()
            base_sym = sym.split(".", 1)[0]
            exchange_value = (h.get("exchange") or inferred or "L")
            exch = exchange_value.upper() if isinstance(exchange_value, str) else "L"

            if "." in sym:
                full_tkr = sym
            else:
                full_tkr = f"{sym}.{exch}"

            sym = (sym or "").upper()
            base_sym, _, resolved_exch = sym.partition(".")
            if resolved_exch:
                exch = resolved_exch.upper()
                full_tkr = sym  # already includes exchange suffix from resolver
            else:
                exch = (h.get("exchange") or inferred or "L").upper()
                full_tkr = f"{base_sym}.{exch}"
            sym = base_sym

            instrument_meta = get_instrument_meta(full_tkr) or _DEFAULT_META.get(full_tkr, {})

            initial_grouping, grouping_source = _first_nonempty_str_with_source(
                ("holding_grouping", h.get("grouping")),
                ("instrument_meta_grouping", instrument_meta.get("grouping")),
                ("holding_sector", h.get("sector")),
                ("instrument_meta_sector", instrument_meta.get("sector")),
                ("holding_region", h.get("region")),
                ("instrument_meta_region", instrument_meta.get("region")),
            )

            row = rows.setdefault(
                full_tkr,
                {
                    "ticker": full_tkr,
                    "exchange": exch,
                    "name": instrument_meta.get("name") or h.get("name", full_tkr),
                    "currency": None,
                    "sector": None,
                    "region": None,
                    "grouping": initial_grouping,
                    "grouping_id": _first_nonempty_str(
                        h.get("grouping_id"),
                        instrument_meta.get("grouping_id"),
                    ),
                    "units": 0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                    "cost_gbp": 0.0,
                    "last_price_gbp": None,
                    "last_price_currency": base_currency,
                    "last_price_date": None,
                    "last_price_time": None,
                    "is_stale": None,
                    "change_7d_pct": None,
                    "change_30d_pct": None,
                    "instrument_type": instrument_meta.get("instrumentType")
                    or instrument_meta.get("instrument_type"),
                    "cost_currency": base_currency,
                    "market_value_currency": base_currency,
                    "gain_currency": base_currency,
                    "_grouping_from_fallback": bool(initial_grouping)
                    and grouping_source in _GROUPING_FALLBACK_SOURCES,
                },
            )
            row["exchange"] = exch
            row.setdefault("_grouping_from_fallback", False)
            row.setdefault("_currency_source", None)
            row.setdefault("_sector_source", None)
            row.setdefault("_region_source", None)

            # accumulate units from the holding
            row["units"] += _safe_num(h.get("units"))

            _update_row_field(row, "currency", h.get("currency"), "holding")
            _update_row_field(row, "sector", h.get("sector"), "holding")
            _update_row_field(row, "region", h.get("region"), "holding")
            _update_row_field(row, "currency", instrument_meta.get("currency"), "instrument_meta")
            _update_row_field(row, "sector", instrument_meta.get("sector"), "instrument_meta")
            _update_row_field(row, "region", instrument_meta.get("region"), "instrument_meta")

            security_meta: Dict[str, Any] | None = None
            if row.get("currency") is None or row.get("sector") is None or row.get("region") is None:
                security_meta = get_security_meta(full_tkr) or {}
                _update_row_field(row, "currency", security_meta.get("currency"), "security_meta")
                _update_row_field(row, "sector", security_meta.get("sector"), "security_meta")
                _update_row_field(row, "region", security_meta.get("region"), "security_meta")
                if security_meta:
                    grouping_pairs: List[tuple[str, Any]] = []
                    if not row.get("_grouping_from_fallback", False):
                        grouping_pairs.append(("current", row.get("grouping")))
                    grouping_pairs.extend(
                        [
                            ("holding_grouping", h.get("grouping")),
                            ("security_meta_grouping", security_meta.get("grouping")),
                            ("instrument_meta_grouping", instrument_meta.get("grouping")),
                            ("row_sector", row.get("sector")),
                            ("holding_sector", h.get("sector")),
                            ("security_meta_sector", security_meta.get("sector")),
                            ("instrument_meta_sector", instrument_meta.get("sector")),
                            ("row_region", row.get("region")),
                            ("holding_region", h.get("region")),
                            ("security_meta_region", security_meta.get("region")),
                            ("instrument_meta_region", instrument_meta.get("region")),
                            ("row_currency", row.get("currency")),
                            ("security_meta_currency", security_meta.get("currency")),
                            ("instrument_meta_currency", instrument_meta.get("currency")),
                        ]
                    )
                    grouping_value, grouping_label = _first_nonempty_str_with_source(*grouping_pairs)
                    if grouping_value:
                        row["grouping"] = grouping_value
                        row["_grouping_from_fallback"] = (
                            grouping_label in _GROUPING_FALLBACK_SOURCES
                        )

                    grouping_id_value, _ = _first_nonempty_str_with_source(
                        ("holding_grouping_id", h.get("grouping_id")),
                        ("security_meta_grouping_id", security_meta.get("grouping_id")),
                        ("instrument_meta_grouping_id", instrument_meta.get("grouping_id")),
                    )
                    if grouping_id_value and not _first_nonempty_str(row.get("grouping_id")):
                        row["grouping_id"] = grouping_id_value

            # attach snapshot if present
            cost_value = h.get("effective_cost_basis_gbp")
            if cost_value is None:
                cost_value = h.get("cost_basis_gbp")
            if cost_value is None:
                cost_value = h.get("cost_gbp")
            cost = _safe_num(cost_value)
            row["cost_gbp"] += cost

            # if holdings already carry market value / gain, include them so we
            # have sensible numbers even when no price snapshot is available
            row["market_value_gbp"] += _safe_num(h.get("market_value_gbp"))
            row["gain_gbp"] += _safe_num(h.get("gain_gbp"))

            # attach snapshot if present – overrides derived values above
            snap = _PRICE_SNAPSHOT.get(full_tkr) or _PRICE_SNAPSHOT.get(base_sym)
            price = snap.get("last_price") if isinstance(snap, dict) else None
            if price and price == price:  # guard against None/NaN/0
                row["last_price_gbp"] = price
                row["last_price_date"] = snap.get("last_price_date")
                row["last_price_time"] = snap.get("last_price_time")
                row["is_stale"] = snap.get("is_stale")
                row["market_value_gbp"] = round(row["units"] * price, 2)
                row["gain_gbp"] = (
                    round(row["market_value_gbp"] - row["cost_gbp"], 2) if row["cost_gbp"] else row["gain_gbp"]
                )

            # ensure percentage change fields are populated
            if row.get("change_7d_pct") is None:
                change_7d = snap.get("change_7d_pct") if isinstance(snap, dict) else None
                if change_7d is None:
                    try:
                        change_7d = instrument_api.price_change_pct(full_tkr, 7)
                    except Exception:
                        change_7d = None
                row["change_7d_pct"] = change_7d
            if row.get("change_30d_pct") is None:
                change_30d = snap.get("change_30d_pct") if isinstance(snap, dict) else None
                if change_30d is None:
                    try:
                        change_30d = instrument_api.price_change_pct(full_tkr, 30)
                    except Exception:
                        change_30d = None
                row["change_30d_pct"] = change_30d

            # pass-through misc attributes (first non-null wins)
            for k in ("asset_class", "industry", "region", "owner", "sector"):
                if k not in row and h.get(k) is not None:
                    row[k] = h[k]

            grouping_name, grouping_id = instrument_api._resolve_grouping_details(
                instrument_meta,
                security_meta,
                h,
                row,
                current=row.get("grouping"),
            )
            if grouping_id:
                row["grouping_id"] = grouping_id
            if grouping_name:
                row["grouping"] = grouping_name
                fallback_candidates = {
                    _first_nonempty_str(row.get("sector")),
                    _first_nonempty_str(h.get("sector")),
                    _first_nonempty_str(row.get("region")),
                    _first_nonempty_str(h.get("region")),
                    _first_nonempty_str(row.get("currency")),
                }
                row["_grouping_from_fallback"] = grouping_name in fallback_candidates

    if os.environ.get("TESTING"):
        for ticker, row in rows.items():
            meta = _DEFAULT_META.get(ticker)
            if not meta:
                continue
            if not _first_nonempty_str(row.get("name")) and meta.get("name"):
                row["name"] = meta["name"]
            if not _first_nonempty_str(row.get("currency")) and meta.get("currency"):
                row["currency"] = meta["currency"]
            if not _first_nonempty_str(row.get("sector")) and meta.get("sector"):
                row["sector"] = meta["sector"]
            if not _first_nonempty_str(row.get("region")) and meta.get("region"):
                row["region"] = meta["region"]
            if not _first_nonempty_str(row.get("grouping")):
                grouping_value = _first_nonempty_str(
                    meta.get("grouping"),
                    meta.get("sector"),
                    meta.get("currency"),
                    meta.get("region"),
                )
                if grouping_value:
                    row["grouping"] = grouping_value
                    row["_grouping_from_fallback"] = True

    rate = _fx_to_base("GBP", base_currency, fx_cache)
    for r in rows.values():
        if rate and rate != 1:
            r["cost_gbp"] = round(_safe_num(r["cost_gbp"]) * rate, 2)
            r["market_value_gbp"] = round(_safe_num(r["market_value_gbp"]) * rate, 2)
            r["gain_gbp"] = round(_safe_num(r["gain_gbp"]) * rate, 2)
            if r.get("last_price_gbp") is not None:
                r["last_price_gbp"] = round(_safe_num(r["last_price_gbp"]) * rate, 4)
            if r.get("day_change_gbp") is not None:
                r["day_change_gbp"] = round(_safe_num(r["day_change_gbp"]) * rate, 2)
        cost = r["cost_gbp"]
        r["gain_pct"] = (r["gain_gbp"] / cost * 100.0) if cost else None
        r["cost_currency"] = base_currency
        r["market_value_currency"] = base_currency
        r["gain_currency"] = base_currency
        if r.get("last_price_gbp") is not None:
            r["last_price_currency"] = base_currency
        if r.get("day_change_gbp") is not None:
            r["day_change_currency"] = base_currency
        if not _first_nonempty_str(r.get("grouping")):
            fallback = _first_nonempty_str(
                r.get("sector"),
                r.get("currency"),
                r.get("region"),
            )
            r["grouping"] = fallback or "Unknown"
            r["grouping_id"] = None
            r["_grouping_from_fallback"] = True
        r.pop("_grouping_from_fallback", None)

    return list(rows.values())


def _aggregate_by_field(portfolio: dict | VirtualPortfolio, field: str, base_currency: str = "GBP") -> List[dict]:
    """Helper to aggregate ticker rows by ``field`` (e.g. sector/region)."""
    rows = aggregate_by_ticker(portfolio, base_currency)
    groups: Dict[str, dict] = {}
    source_priority = {"holding": 3, "security_meta": 2, "instrument_meta": 1}
    for r in rows:
        key_value = r.get(field)
        key = key_value.strip() if isinstance(key_value, str) else None
        source = r.get(f"_{field}_source") or ""
        priority = source_priority.get(source, 0)
        if not key:
            key = "Unknown"
        elif priority < 2:
            key = "Unknown"
        g = groups.setdefault(
            key,
            {
                field: key,
                "market_value_gbp": 0.0,
                "gain_gbp": 0.0,
                "cost_gbp": 0.0,
                "currency": base_currency,
            },
        )
        g["market_value_gbp"] += _safe_num(r.get("market_value_gbp"))
        g["gain_gbp"] += _safe_num(r.get("gain_gbp"))
        g["cost_gbp"] += _safe_num(r.get("cost_gbp"))

    total_cost = sum(g["cost_gbp"] for g in groups.values())
    for g in groups.values():
        cost = g["cost_gbp"]
        g["gain_pct"] = (g["gain_gbp"] / cost * 100.0) if cost else None
        g["contribution_pct"] = (g["gain_gbp"] / total_cost * 100.0) if total_cost else None
    return list(groups.values())


def aggregate_by_sector(portfolio: dict | VirtualPortfolio, base_currency: str = "GBP") -> List[dict]:
    """Return aggregated holdings grouped by sector with return contribution."""
    return _aggregate_by_field(portfolio, "sector", base_currency)


def aggregate_by_region(portfolio: dict | VirtualPortfolio, base_currency: str = "GBP") -> List[dict]:
    """Return aggregated holdings grouped by region with return contribution."""
    return _aggregate_by_field(portfolio, "region", base_currency)


# ──────────────────────────────────────────────────────────────
# Performance helpers
# ──────────────────────────────────────────────────────────────
def compute_owner_performance(
    owner: str, days: int = 365, include_flagged: bool = False, include_cash: bool = True
) -> Dict[str, Any]:
    """Return daily portfolio values and returns for an ``owner``.

    The calculation uses current holdings and fetches closing prices from the
    meta timeseries cache for the requested rolling window. Instruments flagged
    in the price snapshot are skipped unless ``include_flagged`` is ``True``.
    The result is returned as ``{"history": [...], "max_drawdown": float}`` where
    ``history`` is a list of records::

        {
            "date": "2024-01-01",
            "value": 1234.56,
            "daily_return": 0.0012,         # 0.12 %
            "weekly_return": 0.0345,        # 3.45 %
            "cumulative_return": 0.0567,    # 5.67 % from start
            "running_max": 1500.0,          # peak value so far
            "drawdown": -0.18,              # % drop from running max
        }

    Parameters
    ----------
    owner:
        Portfolio owner slug.
    days:
        Number of trailing days of history to include.
    include_cash:
        Whether to include cash holdings in the calculation. When ``False``,
        positions whose ticker starts with ``"CASH"`` are ignored.

    Returns ``{"history": [], "max_drawdown": None}`` if the owner or
    timeseries data is missing.
    """

    try:
        pf = portfolio_mod.build_owner_portfolio(owner)
    except FileNotFoundError:
        raise

    from backend.common import instrument_api

    flagged = {k.upper() for k, v in _PRICE_SNAPSHOT.items() if v.get("flagged")}

    holdings: List[tuple[str, str, float]] = []  # (ticker, exchange, units)
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            if not include_cash and tkr.split(".")[0] == "CASH":
                continue
            units = _safe_num(h.get("units"))
            if not units:
                continue

            resolved = instrument_api._resolve_full_ticker(tkr, _PRICE_SNAPSHOT)
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
                if not h.get("exchange"):
                    logger.debug("Could not resolve exchange for %s; defaulting to L", tkr)
            exch = (h.get("exchange") or inferred or "L").upper()
            full = f"{sym}.{exch}".upper()
            if not include_flagged and full in flagged:
                logger.debug("Skipping flagged instrument %s", full)
                continue
            holdings.append((sym, exch, units))

    if not holdings:
        return {"history": [], "max_drawdown": None}

    total = pd.Series(dtype=float)
    for ticker, exchange, units in holdings:
        df = load_meta_timeseries(ticker, exchange, days)
        if df.empty or "Date" not in df.columns or "Close" not in df.columns:
            continue
        df = df[["Date", "Close"]].copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        values = df.set_index("Date")["Close"] * units
        total = total.add(values, fill_value=0)

    if total.empty:
        return {"history": [], "max_drawdown": None}

    perf = total.sort_index().to_frame(name="value")
    perf["daily_return"] = perf["value"].pct_change()
    perf["weekly_return"] = perf["value"].pct_change(5)
    start_val = perf["value"].iloc[0]
    perf["cumulative_return"] = perf["value"] / start_val - 1
    perf["running_max"] = perf["value"].cummax()
    perf["drawdown"] = perf["value"] / perf["running_max"] - 1
    max_drawdown = float(perf["drawdown"].min())
    perf = perf.reset_index().rename(columns={"index": "date"})

    out: List[Dict] = []
    for row in perf.itertuples(index=False):
        out.append(
            {
                "date": row.Date.isoformat(),
                "value": round(float(row.value), 2),
                "daily_return": (float(row.daily_return) if pd.notna(row.daily_return) else None),
                "weekly_return": (float(row.weekly_return) if pd.notna(row.weekly_return) else None),
                "cumulative_return": (float(row.cumulative_return) if pd.notna(row.cumulative_return) else None),
                "running_max": round(float(row.running_max), 2),
                "drawdown": (float(row.drawdown) if pd.notna(row.drawdown) else None),
            }
        )

    return {"history": out, "max_drawdown": max_drawdown}


def portfolio_value_breakdown(owner: str, date: str) -> List[Dict[str, Any]]:
    """Return each holding's units, price and value for ``date``.

    Parameters
    ----------
    owner:
        Portfolio owner slug.
    date:
        ISO formatted date (``YYYY-MM-DD``) for which to fetch prices.
    """

    try:
        target = datetime.fromisoformat(date).date()
    except ValueError as exc:  # invalid date string
        raise ValueError(f"Invalid date: {date}") from exc

    pf = portfolio_mod.build_owner_portfolio(owner)

    from backend.common import instrument_api

    holdings: Dict[str, Dict[str, Any]] = {}
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            units = _safe_num(h.get("units"))
            if not units:
                continue
            resolved = instrument_api._resolve_full_ticker(tkr, _PRICE_SNAPSHOT)
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
                if not h.get("exchange"):
                    logger.debug("Could not resolve exchange for %s; defaulting to L", tkr)
            exch = (h.get("exchange") or inferred or "L").upper()
            key = f"{sym}.{exch}"
            row = holdings.setdefault(
                key,
                {"ticker": sym, "exchange": exch, "units": 0.0},
            )
            row["units"] += units

    result: List[Dict[str, Any]] = []
    for row in holdings.values():
        price, _src = _get_price_for_date_scaled(row["ticker"], row["exchange"], target)
        if price is not None:
            row["price"] = round(price, 4)
            row["value"] = round(row["units"] * price, 2)
        else:
            row["price"] = None
            row["value"] = None
        result.append(row)

    return result


def _portfolio_value_series(name: str, days: int = 365, *, group: bool = False) -> pd.Series:
    """Helper to compute daily portfolio values for an owner or group."""

    if group:
        pf = group_portfolio.build_group_portfolio(name)
    else:
        pf = portfolio_mod.build_owner_portfolio(name)

    from backend.common import instrument_api

    flagged = {k.upper() for k, v in _PRICE_SNAPSHOT.items() if v.get("flagged")}
    holdings: List[tuple[str, str, float]] = []
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue
            units = _safe_num(h.get("units"))
            if not units:
                continue
            resolved = instrument_api._resolve_full_ticker(tkr, _PRICE_SNAPSHOT)
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
                if not h.get("exchange"):
                    logger.debug("Could not resolve exchange for %s; defaulting to L", tkr)
            exch = (h.get("exchange") or inferred or "L").upper()
            full = f"{sym}.{exch}".upper()
            if full in flagged:
                logger.debug("Skipping flagged instrument %s", full)
                continue
            holdings.append((sym, exch, units))

    total = pd.Series(dtype=float)
    for ticker, exchange, units in holdings:
        df = load_meta_timeseries(ticker, exchange, days)
        if df.empty or "Date" not in df.columns or "Close" not in df.columns:
            continue
        df = df[["Date", "Close"]].copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        values = df.set_index("Date")["Close"] * units
        total = total.add(values, fill_value=0)

    return total.sort_index()


def _alpha_vs_benchmark(
    name: str,
    benchmark: str,
    days: int = 365,
    *,
    group: bool = False,
    include_breakdown: bool = False,
) -> tuple[float | None, dict[str, Any]]:
    total = _portfolio_value_series(name, days, group=group)
    if total.empty:
        return None, {"series": [], "portfolio_cumulative_return": None, "benchmark_cumulative_return": None}
    port_ret = total.pct_change().dropna()

    bench_tkr, bench_exch = (benchmark.split(".", 1) + ["L"])[:2]
    df = load_meta_timeseries(bench_tkr, bench_exch, days)
    if df.empty or "Close" not in df.columns or "Date" not in df.columns:
        return None, {"series": [], "portfolio_cumulative_return": None, "benchmark_cumulative_return": None}
    df = df[["Date", "Close"]].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    bench_ret = df.set_index("Date")["Close"].pct_change().dropna()

    port_ret, bench_ret = port_ret.align(bench_ret, join="inner")
    if port_ret.empty:
        return None, {"series": [], "portfolio_cumulative_return": None, "benchmark_cumulative_return": None}

    aligned = pd.DataFrame({"portfolio": port_ret, "benchmark": bench_ret})
    aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna()

    # Daily returns above 1,000% are almost certainly data errors (for example
    # when a benchmark trades near zero).  Drop those rows before computing
    # cumulative performance.
    max_reasonable_return = 10.0
    aligned = aligned[(aligned.abs() <= max_reasonable_return).all(axis=1)]
    if aligned.empty:
        return None, {"series": [], "portfolio_cumulative_return": None, "benchmark_cumulative_return": None}

    port_cum_series = (1 + aligned["portfolio"]).cumprod() - 1
    bench_cum_series = (1 + aligned["benchmark"]).cumprod() - 1
    value = float(port_cum_series.iloc[-1] - bench_cum_series.iloc[-1])

    if not include_breakdown:
        return value, {}

    breakdown_series: list[dict[str, Any]] = []
    for idx, _row in aligned.iterrows():
        breakdown_series.append(
            {
                "date": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "portfolio_cumulative_return": float(port_cum_series.loc[idx]),
                "benchmark_cumulative_return": float(bench_cum_series.loc[idx]),
                "excess_cumulative_return": float(
                    port_cum_series.loc[idx] - bench_cum_series.loc[idx]
                ),
            }
        )

    breakdown = {
        "series": breakdown_series,
        "portfolio_cumulative_return": float(port_cum_series.iloc[-1]),
        "benchmark_cumulative_return": float(bench_cum_series.iloc[-1]),
    }
    return value, breakdown


def _tracking_error(
    name: str,
    benchmark: str,
    days: int = 365,
    *,
    group: bool = False,
    include_breakdown: bool = False,
) -> tuple[float | None, dict[str, Any]]:
    total = _portfolio_value_series(name, days, group=group)
    if total.empty:
        return None, {"active_returns": [], "daily_active_standard_deviation": None}
    port_ret = total.pct_change().dropna()

    bench_tkr, bench_exch = (benchmark.split(".", 1) + ["L"])[:2]
    df = load_meta_timeseries(bench_tkr, bench_exch, days)
    if df.empty or "Close" not in df.columns or "Date" not in df.columns:
        return None, {"active_returns": [], "daily_active_standard_deviation": None}
    df = df[["Date", "Close"]].copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    bench_ret = df.set_index("Date")["Close"].pct_change().dropna()

    port_ret, bench_ret = port_ret.align(bench_ret, join="inner")
    if port_ret.empty:
        return None, {"active_returns": [], "daily_active_standard_deviation": None}
    aligned = pd.DataFrame({"portfolio": port_ret, "benchmark": bench_ret})
    aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna()
    aligned["active"] = aligned["portfolio"] - aligned["benchmark"]
    if aligned["active"].count() < 2:
        return None, {"active_returns": [], "daily_active_standard_deviation": None}
    std = aligned["active"].std()
    if not math.isfinite(std):
        return None, {"active_returns": [], "daily_active_standard_deviation": None}
    annualised = float(std * math.sqrt(252))

    if not include_breakdown:
        return annualised, {}

    active_rows: list[dict[str, Any]] = []
    for idx, row in aligned.iterrows():
        active_rows.append(
            {
                "date": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "portfolio_return": float(row["portfolio"]),
                "benchmark_return": float(row["benchmark"]),
                "active_return": float(row["active"]),
            }
        )

    breakdown = {
        "active_returns": active_rows,
        "daily_active_standard_deviation": float(std),
    }
    return annualised, breakdown


def _max_drawdown(
    name: str,
    days: int = 365,
    *,
    group: bool = False,
    include_breakdown: bool = False,
) -> tuple[float | None, dict[str, Any]]:
    total = _portfolio_value_series(name, days, group=group)
    if total.empty:
        return None, {"series": [], "peak": None, "trough": None}
    running_max = total.cummax()
    drawdown = total / running_max - 1
    min_drawdown = drawdown.min()
    value = float(min_drawdown) if math.isfinite(min_drawdown) else None

    if not include_breakdown:
        return value, {}

    series: list[dict[str, Any]] = []
    for idx, val in total.items():
        series.append(
            {
                "date": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "portfolio_value": float(val),
                "running_max": float(running_max.loc[idx]),
                "drawdown": float(drawdown.loc[idx]),
            }
        )

    peak_info: dict[str, Any] | None = None
    trough_info: dict[str, Any] | None = None
    if value is not None:
        trough_date = drawdown.idxmin()
        if trough_date is not None:
            trough_val = float(total.loc[trough_date])
            trough_info = {
                "date": trough_date.isoformat() if hasattr(trough_date, "isoformat") else str(trough_date),
                "value": trough_val,
                "drawdown": float(drawdown.loc[trough_date]),
            }
            peak_series = running_max.loc[:trough_date]
            if not peak_series.empty:
                peak_value = float(peak_series.max())
                peak_date_candidates = peak_series[peak_series == peak_value]
                if not peak_date_candidates.empty:
                    peak_date = peak_date_candidates.index[0]
                    peak_info = {
                        "date": peak_date.isoformat()
                        if hasattr(peak_date, "isoformat")
                        else str(peak_date),
                        "value": peak_value,
                    }

    breakdown = {"series": series, "peak": peak_info, "trough": trough_info}
    return value, breakdown


def compute_alpha_vs_benchmark(
    owner: str, benchmark: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _alpha_vs_benchmark(
        owner, benchmark, days, include_breakdown=include_breakdown
    )
    if include_breakdown:
        return value, breakdown
    return value


def compute_group_alpha_vs_benchmark(
    slug: str, benchmark: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _alpha_vs_benchmark(
        slug, benchmark, days, group=True, include_breakdown=include_breakdown
    )
    if include_breakdown:
        return value, breakdown
    return value


def compute_tracking_error(
    owner: str, benchmark: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _tracking_error(
        owner, benchmark, days, include_breakdown=include_breakdown
    )
    if include_breakdown:
        return value, breakdown
    return value


def compute_group_tracking_error(
    slug: str, benchmark: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _tracking_error(
        slug, benchmark, days, group=True, include_breakdown=include_breakdown
    )
    if include_breakdown:
        return value, breakdown
    return value


def compute_max_drawdown(
    owner: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _max_drawdown(owner, days, include_breakdown=include_breakdown)
    if include_breakdown:
        return value, breakdown
    return value


def compute_group_max_drawdown(
    slug: str, days: int = 365, *, include_breakdown: bool = False
) -> float | None | tuple[float | None, dict[str, Any]]:
    value, breakdown = _max_drawdown(
        slug, days, group=True, include_breakdown=include_breakdown
    )
    if include_breakdown:
        return value, breakdown
    return value


# ──────────────────────────────────────────────────────────────
# Return metrics
# ──────────────────────────────────────────────────────────────
def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val)).date()
    except Exception:
        return None


_CASH_FLOW_SIGNS = {
    "DEPOSIT": 1,
    "WITHDRAWAL": -1,
    "DIVIDENDS": 1,
    "INTEREST": 1,
}


def compute_time_weighted_return(owner: str, days: int = 365) -> float | None:
    """Compute time-weighted return for ``owner`` over ``days``."""

    total = _portfolio_value_series(owner, days)
    if total.empty or len(total) < 2:
        return None

    start = total.index.min()
    end = total.index.max()

    txs = load_transactions(owner)
    flows: defaultdict[date, float] = defaultdict(float)
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d or d < start or d > end:
            continue
        typ = (t.get("type") or t.get("kind") or "").upper()
        if typ in _CASH_FLOW_SIGNS:
            try:
                amt = float(t.get("amount_minor") or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
            flows[d] += amt * _CASH_FLOW_SIGNS[typ]

    twr = 1.0
    prev_val = float(total.iloc[0])
    for d, val in total.iloc[1:].items():
        cf = flows.get(d, 0.0)
        if prev_val:
            r = (val - cf) / prev_val - 1.0
            twr *= 1.0 + r
        prev_val = val

    return float(twr - 1.0)


def compute_xirr(owner: str, days: int = 365) -> float | None:
    """Compute XIRR for ``owner`` over ``days`` using cash flows."""

    total = _portfolio_value_series(owner, days)
    if total.empty:
        return None

    start = total.index.min()
    end = total.index.max()

    txs = load_transactions(owner)
    flows: list[tuple[date, float]] = []
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d or d < start or d > end:
            continue
        typ = (t.get("type") or t.get("kind") or "").upper()
        if typ in _CASH_FLOW_SIGNS:
            try:
                amt = float(t.get("amount_minor") or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
            sign = 1 if _CASH_FLOW_SIGNS[typ] < 0 else -1
            flows.append((d, amt * sign))

    flows.append((end, float(total.iloc[-1])))
    if len(flows) < 2:
        return None

    flows.sort(key=lambda x: x[0])
    start = flows[0][0]

    def xnpv(rate: float) -> float:
        return sum(amt / (1.0 + rate) ** ((d - start).days / 365.0) for d, amt in flows)

    rate = 0.1
    converged = False
    for _ in range(100):
        try:
            f = float(xnpv(rate))
        except (OverflowError, ValueError, TypeError):
            return None
        if abs(f) < 1e-6:
            converged = True
            break
        try:
            df = float(
                sum(
                    -((d - start).days / 365.0) * amt / (1.0 + rate) ** ((d - start).days / 365.0 + 1)
                    for d, amt in flows
                )
            )
        except (OverflowError, ValueError, TypeError):
            return None
        if df == 0 or not math.isfinite(df):
            return None
        rate_new = rate - f / df
        if not math.isfinite(rate_new) or rate_new <= -1:
            return None
        if abs(rate_new - rate) < 1e-7:
            rate = rate_new
            converged = True
            break
        rate = rate_new

    if not converged or not math.isfinite(rate):
        return None
    return float(rate)


def compute_cagr(owner: str, days: int = 365) -> float | None:
    """Compute the portfolio CAGR for ``owner`` over ``days``."""

    total = _portfolio_value_series(owner, days)
    if total.empty or len(total) < 2:
        return None

    start_val = float(total.iloc[0])
    end_val = float(total.iloc[-1])
    years = (total.index[-1] - total.index[0]).days / 365.0
    if start_val <= 0 or years <= 0:
        return None
    return float((end_val / start_val) ** (1 / years) - 1)


def _cash_value_series(owner: str, days: int = 365) -> pd.Series:
    """Helper to compute daily cash values for an owner."""

    pf = portfolio_mod.build_owner_portfolio(owner)
    from backend.common import instrument_api

    holdings: list[tuple[str, str, float]] = []
    for acct in pf.get("accounts", []):
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr.startswith("CASH"):
                continue
            units = _safe_num(h.get("units"))
            if not units:
                continue
            resolved = instrument_api._resolve_full_ticker(tkr, _PRICE_SNAPSHOT)
            if resolved:
                sym, inferred = resolved
            else:
                sym, inferred = (tkr.split(".", 1) + [None])[:2]
            exch = (h.get("exchange") or inferred or "GBP").upper()
            holdings.append((sym, exch, units))

    total = pd.Series(dtype=float)
    for ticker, exchange, units in holdings:
        df = load_meta_timeseries(ticker, exchange, days)
        if df.empty or "Date" not in df.columns or "Close" not in df.columns:
            continue
        df = df[["Date", "Close"]].copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        values = df.set_index("Date")["Close"] * units
        total = total.add(values, fill_value=0)

    return total.sort_index()


def compute_cash_apy(owner: str, days: int = 365) -> float | None:
    """Compute the APY of cash holdings for ``owner`` over ``days``."""

    total = _cash_value_series(owner, days)
    if total.empty or len(total) < 2:
        return None

    start_val = float(total.iloc[0])
    end_val = float(total.iloc[-1])
    years = (total.index[-1] - total.index[0]).days / 365.0
    if start_val <= 0 or years <= 0:
        return None
    return float((end_val / start_val) ** (1 / years) - 1)


# ──────────────────────────────────────────────────────────────
# Snapshot refresher (used by /prices/refresh)
# ──────────────────────────────────────────────────────────────
def refresh_snapshot_in_memory_from_timeseries(days: int = 365) -> None:
    """
    Pull a closing-price snapshot from the meta timeseries cache
    and write it to *data/prices/latest_prices.json* in the canonical
    shape used by the rest of the backend.
    """
    tickers = list_all_unique_tickers()
    snapshot: Dict[str, Dict[str, str | float]] = {}
    from backend.common import instrument_api

    for t in tickers:
        try:
            today = datetime.today().date()
            cutoff = today - timedelta(days=days)
            resolved = instrument_api._resolve_full_ticker(t, _PRICE_SNAPSHOT)
            if resolved:
                ticker_only, exchange = resolved
            else:
                ticker_only = t.split(".", 1)[0]
                exchange = "L"
                logger.debug("Could not resolve exchange for %s; defaulting to L", t)

            df = load_meta_timeseries_range(
                ticker=ticker_only,
                exchange=exchange,
                start_date=cutoff,
                end_date=today,
            )

            if df is not None and not df.empty:
                # apply scaling overrides (e.g., GBX -> GBP)
                scale = get_scaling_override(ticker_only, exchange, None)
                df = apply_scaling(df, scale)
                if scale != 1 and "Close_gbp" in df.columns:
                    df["Close_gbp"] = pd.to_numeric(df["Close_gbp"], errors="coerce") * scale

                # Map lowercase column names to their actual counterparts
                name_map = {c.lower(): c for c in df.columns}

                close_col = (
                    name_map.get("close_gbp")
                    or name_map.get("close")
                    or name_map.get("adj close")
                    or name_map.get("adj_close")
                )
                if close_col:
                    latest_row = df.iloc[-1]
                    snapshot[t] = {
                        "last_price": float(latest_row[close_col]),
                        "last_price_date": pd.to_datetime(latest_row["Date"]).strftime("%Y-%m-%d"),
                    }
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            logger.warning("Could not get timeseries for %s: %s", t, e)

    # store in-memory
    refresh_snapshot_in_memory(snapshot, datetime.now(UTC))

    # write to disk
    try:
        if _PRICES_PATH:
            _PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PRICES_PATH.write_text(json.dumps(snapshot, indent=2))
            logger.info("Wrote %d prices to %s", len(snapshot), _PRICES_PATH)
        else:
            logger.info(
                "Price snapshot path not configured; skipping write (expected when config.prices_json is unset)"
            )
    except OSError as e:
        logger.warning("Failed to write latest_prices.json: %s", e)

    logger.info("Refreshed %d price entries", len(snapshot))


def refresh_snapshot_async(days: int = 365) -> asyncio.Task:
    """Run :func:`refresh_snapshot_in_memory_from_timeseries` in the background."""

    async def _runner() -> None:
        try:
            await asyncio.to_thread(refresh_snapshot_in_memory_from_timeseries, days=days)
        except asyncio.CancelledError:  # pragma: no cover - defensive
            logger.info("refresh_snapshot_async cancelled")
            raise

    return asyncio.create_task(_runner())


# ──────────────────────────────────────────────────────────────
# Alert helpers
# ──────────────────────────────────────────────────────────────
def check_price_alerts(threshold_pct: float = 0.1) -> List[Dict]:
    """Check holdings against cost basis and emit alerts."""
    from backend.common.alerts import publish_alert

    alerts: List[Dict] = []
    for pf in list_portfolios():
        for row in aggregate_by_ticker(pf):
            cost = _safe_num(row.get("cost_gbp"))
            mv = _safe_num(row.get("market_value_gbp"))
            if cost <= 0 or mv <= 0:
                continue
            change_pct = (mv - cost) / cost
            if abs(change_pct) >= threshold_pct:
                ticker = row["ticker"]
                alert = {
                    "ticker": ticker,
                    "change_pct": round(change_pct, 4),
                    "message": f"{ticker} change {change_pct*100:.1f}% vs cost basis",
                }
                publish_alert(alert)
                alerts.append(alert)
    return alerts
