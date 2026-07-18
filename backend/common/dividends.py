"""Automated dividend collection.

Fetches declared dividends for held tickers via yfinance and records them as
``DIVIDEND`` transactions, so dividend income no longer has to be entered by
hand. See issue #2750.

Design notes / known v1 limitations
------------------------------------
* Transaction type literal: this module writes ``DIVIDEND`` to match the
  income-reporting path (``backend/reports.py``, ``backend/utils/positions.py``)
  and the issue's stated acceptance criteria. The cash-flow sign tables in
  ``portfolio_loader.py`` and ``portfolio_utils.py`` (used by TWR/XIRR) also
  recognise ``DIVIDEND`` alongside the legacy ``DIVIDENDS`` literal (#4948),
  so both transaction-type spellings are treated consistently everywhere.
* Amount calculation: yfinance's ``Ticker.dividends`` returns a per-share
  amount, not the total cash received. This module multiplies the per-share
  amount by the unit count held as of the dividend's ex-date, reconstructed
  from the transaction log via
  :func:`backend.common.portfolio_loader.get_units_as_of` (#4947), so a buy or
  sell between the ex-date and when this job runs does not skew the recorded
  amount.
* Idempotency: the transaction store has no uniqueness constraint, so this
  module de-duplicates by scanning existing ``DIVIDEND`` transactions for a
  matching ``(ticker, ex_date)`` pair before writing.
* First run per ticker: when no prior ``DIVIDEND`` transaction exists for a
  ticker, only dividends declared within the last ``_DEFAULT_LOOKBACK_DAYS``
  days are imported (not full history), to avoid surprise historical backfill
  on the first scheduled run for an existing holding.
* Provider: v1 uses yfinance only. The issue's Alpha Vantage fallback is
  deferred — Alpha Vantage's free tier is heavily rate-limited per-key, which
  doesn't suit a job that queries every held ticker on a schedule, and
  yfinance is already the provider used elsewhere in this codebase (price
  refresh). Revisit if yfinance reliability becomes a problem in practice.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf

from backend.common.accounts_store import LocalAccountsStore, S3AccountsStore
from backend.common.currency import CurrencyNormaliser
from backend.common.data_loader import DATA_BUCKET_ENV
from backend.common.instruments import get_instrument_meta
from backend.common.portfolio_loader import get_units_as_of
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger("dividends")

DIVIDEND_TRANSACTION_TYPE = "DIVIDEND"

# When a ticker has no prior recorded DIVIDEND transaction, only import
# declarations from within this many days rather than full provider history.
_DEFAULT_LOOKBACK_DAYS = 90


def _resolve_store() -> "LocalAccountsStore | S3AccountsStore":
    """Return the writable accounts store for the current environment.

    Mirrors ``backend.routes.transactions.resolve_writable_store`` but has no
    ``Request`` to read overrides from, since this runs outside an HTTP
    request (scheduled Lambda / CLI invocation).
    """
    if config.app_env == "aws":
        bucket = os.getenv(DATA_BUCKET_ENV)
        if bucket:
            return S3AccountsStore(bucket=bucket)
        logger.warning("%s is not set; falling back to local accounts store.", DATA_BUCKET_ENV)
    root = config.accounts_root
    return LocalAccountsStore(root=Path(root) if root else None)


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _dividend_key(ticker: str, ex_date: str) -> tuple[str, str]:
    return (ticker.upper(), (ex_date or "")[:10])


def _last_dividend_dates(transactions: List[Dict[str, Any]]) -> Dict[str, date]:
    """Return the most recent recorded DIVIDEND ex-date per ticker."""
    last: Dict[str, date] = {}
    for t in transactions:
        if (t.get("type") or "").upper() != DIVIDEND_TRANSACTION_TYPE:
            continue
        ticker = str(t.get("ticker") or "").upper()
        tx_date = _parse_date(t.get("date"))
        if not ticker or tx_date is None:
            continue
        if ticker not in last or tx_date > last[ticker]:
            last[ticker] = tx_date
    return last


def _held_units(holdings_doc: Dict[str, Any], ticker: str) -> float:
    for h in holdings_doc.get("holdings", []) or []:
        if str(h.get("ticker") or "").upper() == ticker:
            try:
                return float(h.get("units") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _fetch_new_dividends(ticker: str, *, since: Optional[date]) -> Optional[List[Dict[str, Any]]]:
    """Return dividend declarations for ``ticker`` after ``since``.

    Returns ``None`` only when the provider call itself raises — callers
    should skip the ticker, not error the whole run. Returns an empty list
    both when the ticker has no qualifying dividends and when yfinance
    returns an empty series for a ticker it doesn't recognise (the two are
    indistinguishable from an empty series alone); either way, no exception
    means no skip.
    """
    try:
        series = yf.Ticker(ticker).dividends
    except Exception as exc:  # pragma: no cover - defensive; provider errors vary
        logger.warning(
            "yfinance dividend fetch failed for %s: %s",
            sanitise_log_value(ticker),
            sanitise_log_value(str(exc)),
        )
        return None

    if series is None or series.empty:
        # An empty series does not distinguish "unrecognised ticker" from
        # "recognised ticker that simply doesn't pay dividends" (e.g. most
        # growth stocks) — yfinance returns an empty series for both rather
        # than raising. Treating this as "no new dividends" (not a skip)
        # avoids permanently flagging legitimate non-dividend-paying
        # holdings as unrecognised on every run. Only an actual exception
        # from the provider call above is treated as unrecognised/skipped.
        return []

    cutoff = since or (date.today() - timedelta(days=_DEFAULT_LOOKBACK_DAYS))
    declarations: List[Dict[str, Any]] = []
    for ts, amount in series.items():
        ex_date = ts.date() if hasattr(ts, "date") else ts
        if not isinstance(ex_date, date) or ex_date <= cutoff:
            continue
        try:
            amount_per_share = float(amount)
        except (TypeError, ValueError):
            continue
        if amount_per_share <= 0:
            continue
        declarations.append({"ex_date": ex_date.isoformat(), "amount_per_share": amount_per_share})
    return declarations


def _amount_minor_gbp(ticker: str, amount_per_share: float, units: float) -> Optional[int]:
    """Return the approximate total dividend amount in GBP minor units (pence)."""
    try:
        meta = get_instrument_meta(ticker) or {}
    except Exception:  # pragma: no cover - defensive; metadata lookups are best-effort
        meta = {}
    raw_currency = str(meta.get("currency") or "GBP").strip()
    normaliser = CurrencyNormaliser.from_raw(raw_currency)
    try:
        per_share_gbp = normaliser.to_gbp(amount_per_share)
    except ValueError:
        return None
    total_gbp = per_share_gbp * units
    return round(total_gbp * 100)


def refresh_dividends() -> Dict[str, Any]:
    """Fetch and record new dividend transactions for every held ticker.

    For each owner/account with holdings, fetches dividends declared since
    the last recorded ``DIVIDEND`` transaction for that ticker (or the last
    ``_DEFAULT_LOOKBACK_DAYS`` days if none), skips tickers the provider
    doesn't recognise, and writes new ``DIVIDEND`` transactions — deduplicated
    on ``(ticker, ex_date)`` so re-running the job does not create duplicates.
    """
    store = _resolve_store()
    summary: Dict[str, Any] = {
        "accounts_processed": 0,
        "tickers_processed": 0,
        "dividends_created": 0,
        "skipped_tickers": [],
    }

    accounts = [(owner, account) for owner, account, _ in store.iter_transaction_documents()]

    for owner, account in accounts:
        holdings_doc = store.read_document(owner, f"{account}.json") or {}
        tickers = sorted(
            {str(h.get("ticker")).upper() for h in holdings_doc.get("holdings", []) or [] if h.get("ticker")}
        )
        if not tickers:
            continue
        summary["accounts_processed"] += 1

        with store.edit_document(
            owner,
            f"{account}_transactions.json",
            default={"owner": owner, "account_type": account, "transactions": []},
        ) as data:
            transactions = data.setdefault("transactions", [])
            existing_keys = {
                _dividend_key(t.get("ticker") or "", t.get("date") or "")
                for t in transactions
                if (t.get("type") or "").upper() == DIVIDEND_TRANSACTION_TYPE
            }
            last_dates = _last_dividend_dates(transactions)

            for ticker in tickers:
                summary["tickers_processed"] += 1
                units = _held_units(holdings_doc, ticker)
                if not units:
                    continue

                declarations = _fetch_new_dividends(ticker, since=last_dates.get(ticker))
                if declarations is None:
                    summary["skipped_tickers"].append(ticker)
                    continue

                for decl in declarations:
                    key = _dividend_key(ticker, decl["ex_date"])
                    if key in existing_keys:
                        continue
                    units_as_of_ex_date = get_units_as_of(data, ticker, decl["ex_date"])
                    if not units_as_of_ex_date:
                        continue
                    amount_minor = _amount_minor_gbp(ticker, decl["amount_per_share"], units_as_of_ex_date)
                    if amount_minor is None or amount_minor <= 0:
                        continue
                    transactions.append(
                        {
                            "type": DIVIDEND_TRANSACTION_TYPE,
                            "ticker": ticker,
                            "date": decl["ex_date"],
                            "amount_minor": amount_minor,
                            "currency": "GBP",
                            "reason": "Automated dividend import",
                            "comments": (
                                f"{ticker} dividend {decl['amount_per_share']:.4f}/share "
                                f"x {units_as_of_ex_date:g} units"
                            ),
                        }
                    )
                    existing_keys.add(key)
                    summary["dividends_created"] += 1

        store.rebuild_portfolio(owner, account)

    return summary
