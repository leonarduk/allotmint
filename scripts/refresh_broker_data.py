#!/usr/bin/env python3
"""Refresh brokerage data via Plaid and merge into S3.

The script can be executed manually or deployed as an AWS Lambda function.
It expects Plaid credentials to be supplied via environment variables and a
JSON mapping of access tokens. The mapping structure is::

    {
        "alex": {"isa": "access-token-1", "sipp": "access-token-2"},
        "joe": {"isa": "token"}
    }

Usage (local cron)::

    python scripts/refresh_broker_data.py tokens.json

When used as a Lambda, set the ``PLAID_ACCESS_TOKENS`` environment variable to
the JSON string.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from typing import Dict, Iterable, Optional

try:  # pragma: no cover - plaid is optional in CI
    from plaid import ApiClient  # type: ignore
    from plaid.api import plaid_api  # type: ignore
    from plaid.model.products import Products  # noqa: F401
    from plaid.model.country_code import CountryCode  # noqa: F401
except Exception:  # pragma: no cover
    ApiClient = None  # type: ignore
    plaid_api = None  # type: ignore

from backend.common.broker_importer import BrokerConfig, BrokerImporter


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _plaid_client() -> plaid_api.PlaidApi:  # type: ignore[name-defined]
    if ApiClient is None:
        raise RuntimeError("plaid-python is required for refresh_broker_data")
    configuration = ApiClient.Configuration(
        host=os.environ.get("PLAID_HOST", "https://sandbox.plaid.com")
    )
    client = plaid_api.PlaidApi(ApiClient(configuration))
    client.api_client.configuration.api_key["clientId"] = os.environ["PLAID_CLIENT_ID"]
    client.api_client.configuration.api_key["secret"] = os.environ["PLAID_SECRET"]
    return client


def refresh(tokens: Dict[str, Dict[str, str]]) -> None:
    client = _plaid_client()
    bucket = os.environ["DATA_BUCKET"]
    importer = BrokerImporter(client, bucket=bucket)
    end = dt.date.today()
    start = end - dt.timedelta(days=30)

    for owner, accounts in tokens.items():
        for account, token in accounts.items():
            cfg = BrokerConfig(owner=owner, account=account, access_token=token)
            importer.refresh(cfg, start, end)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh brokerage data via Plaid")
    parser.add_argument("tokens", help="Path to JSON file with access tokens")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    with open(args.tokens, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    refresh(tokens)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):  # pragma: no cover - simple wrapper
    tokens = json.loads(os.environ["PLAID_ACCESS_TOKENS"])
    refresh(tokens)
    return {"status": "ok"}


if __name__ == "__main__":
    main()
