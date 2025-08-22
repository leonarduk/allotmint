from __future__ import annotations

"""Brokerage API importer for holdings and transactions.

This module provides a thin wrapper around Plaid's Investments API to pull
holdings and transaction data for AllotMint.

The design allows plugging in broker specific APIs by implementing the same
interface used here. Only the Plaid workflow is implemented for now because it
supports many UK brokers and provides a consistent schema.

Other brokerage APIs such as E*TRADE, Interactive Brokers or Alpaca expose
REST interfaces for similar data. They can be integrated by writing additional
fetchers that conform to the ``BrokerImporter`` contract.
"""

import datetime as dt
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

try:  # pragma: no cover - plaid is optional in CI
    from plaid import ApiClient  # type: ignore
    from plaid.api import plaid_api  # type: ignore
    from plaid.model.investments_holdings_get_request import (
        InvestmentsHoldingsGetRequest,
    )
    from plaid.model.investments_transactions_get_request import (
        InvestmentsTransactionsGetRequest,
    )
except Exception:  # pragma: no cover - keep optional
    ApiClient = None  # type: ignore
    plaid_api = None  # type: ignore

import boto3

logger = logging.getLogger(__name__)


@dataclass
class BrokerConfig:
    """Configuration for a single brokerage access token."""

    owner: str
    account: str
    access_token: str


class BrokerImporter:
    """Import holdings and transactions via Plaid and store in S3.

    Parameters
    ----------
    api_client:
        Instance of ``plaid_api.PlaidApi``.
    bucket:
        S3 bucket name used for account and transaction storage.
    """

    def __init__(self, api_client: plaid_api.PlaidApi, bucket: str) -> None:  # type: ignore[name-defined]
        if api_client is None or ApiClient is None:
            raise RuntimeError(
                "plaid-python is required for BrokerImporter but is not installed"
            )
        self.client = api_client
        self.bucket = bucket
        self.s3 = boto3.client("s3")

    # ------------------------------------------------------------------
    # Plaid helpers
    # ------------------------------------------------------------------
    def _fetch_holdings(self, token: str) -> List[Dict[str, Any]]:
        req = InvestmentsHoldingsGetRequest(access_token=token)
        resp = self.client.investments_holdings_get(req)
        results: List[Dict[str, Any]] = []
        for h in resp.holdings:
            sec = resp.securities_dict.get(h.security_id)
            ticker = getattr(sec, "ticker_symbol", None) or sec.cusip or sec.name
            results.append(
                {
                    "ticker": ticker,
                    "units": float(h.quantity),
                    "cost_basis_gbp": float(h.cost_basis or 0.0),
                    "acquired_date": h.last_purchase_date,
                }
            )
        return results

    def _fetch_transactions(
        self, token: str, start: dt.date, end: dt.date
    ) -> List[Dict[str, Any]]:
        req = InvestmentsTransactionsGetRequest(
            access_token=token, start_date=start, end_date=end
        )
        resp = self.client.investments_transactions_get(req)
        txs: List[Dict[str, Any]] = []
        for t in resp.transactions:
            sec = resp.securities_dict.get(t.security_id)
            ticker = getattr(sec, "ticker_symbol", None) or sec.cusip or sec.name
            txs.append(
                {
                    "date": t.date.isoformat(),
                    "ticker": ticker,
                    "type": t.type,
                    "quantity": float(t.quantity),
                    "price": float(t.price),
                }
            )
        return txs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self, cfg: BrokerConfig, start: dt.date, end: dt.date) -> None:
        """Fetch holdings and transactions and merge into S3.

        Parameters
        ----------
        cfg:
            Broker configuration containing access token and destination info.
        start, end:
            Date range for transactions.
        """

        holdings = self._fetch_holdings(cfg.access_token)
        txs = self._fetch_transactions(cfg.access_token, start, end)

        self._merge_holdings(cfg, holdings)
        self._merge_transactions(cfg, txs)

    # ------------------------------------------------------------------
    # S3 helpers
    # ------------------------------------------------------------------
    def _merge_holdings(self, cfg: BrokerConfig, holdings: List[Dict[str, Any]]) -> None:
        key = f"accounts/{cfg.owner}/{cfg.account}.json"
        payload = {
            "owner": cfg.owner,
            "account_type": cfg.account.upper(),
            "currency": "GBP",
            "last_updated": dt.date.today().isoformat(),
            "holdings": holdings,
        }
        self.s3.put_object(
            Bucket=self.bucket, Key=key, Body=json.dumps(payload).encode("utf-8")
        )
        logger.info("Uploaded holdings for %s/%s", cfg.owner, cfg.account)

    def _merge_transactions(
        self, cfg: BrokerConfig, transactions: List[Dict[str, Any]]
    ) -> None:
        key = f"transactions/{cfg.owner}/{cfg.account.lower()}_transactions.json"
        existing: List[Dict[str, Any]] = []
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
            data = json.loads(obj["Body"].read())
            existing = data.get("transactions", [])
        except self.s3.exceptions.NoSuchKey:
            pass
        existing.extend(transactions)
        # dedupe by date, ticker, quantity, price
        dedup: List[Dict[str, Any]] = []
        seen = set()
        for tx in sorted(existing, key=lambda x: x.get("date")):
            key = (
                tx.get("date"),
                tx.get("ticker"),
                tx.get("quantity"),
                tx.get("price"),
            )
            if key in seen:
                continue
            seen.add(key)
            dedup.append(tx)
        payload = {
            "owner": cfg.owner,
            "account_type": cfg.account.upper(),
            "currency": "GBP",
            "last_updated": dt.date.today().isoformat(),
            "transactions": dedup,
        }
        self.s3.put_object(
            Bucket=self.bucket, Key=key, Body=json.dumps(payload).encode("utf-8")
        )
        logger.info("Uploaded %d transactions for %s/%s", len(dedup), cfg.owner, cfg.account)


__all__ = ["BrokerImporter", "BrokerConfig"]
