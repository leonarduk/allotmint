"""Lambda entry point to refresh prices on a schedule.

After refreshing prices the optional trading agent can be triggered. The
behaviour is controlled via the ``ALLOTMINT_ENABLE_TRADING_AGENT`` environment
variable so deployments can enable or disable automated trading without code
changes.

Failure handling
----------------
When invoked synchronously by the CDK deploy Trigger (REQUEST_RESPONSE), an
unhandled exception causes CloudFormation to roll back the entire stack.  To
avoid that regression, ``lambda_handler`` catches all exceptions from
``refresh_prices()``, logs the error, writes an empty stub snapshot so the
"price snapshot not yet seeded" CloudWatch warning is suppressed on subsequent
cold starts, and returns normally.  Real prices will be populated on the next
scheduled EventBridge invocation.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from backend.common.portfolio_utils import DATA_BUCKET_ENV, PRICES_S3_KEY
from backend.common.prices import refresh_prices
from backend.config import config

try:  # trading agent is optional; skip if missing
    import trading_agent  # type: ignore
except Exception:  # pragma: no cover - only hit when package missing
    trading_agent = None

logger = logging.getLogger("prices")


def _seed_empty_snapshot() -> None:
    """Upload an empty price snapshot to S3 so cold-start warnings are suppressed.

    Called only when ``refresh_prices()`` raises — ensures the S3 key exists so
    ``portfolio_utils._load_price_snapshot_from_s3`` does not log the
    "Price snapshot not yet present" warning on every Lambda invocation.
    The next successful scheduled refresh will overwrite this stub with real data.
    """
    # Skip in non-AWS environments (local, staging) where the data bucket may
    # not exist.  Only the AWS deployment has a real S3 bucket to write to.
    if config.app_env != "aws":
        return
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        return
    try:
        import boto3  # type: ignore

        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=PRICES_S3_KEY,
            Body=b"{}",
            ContentType="application/json",
        )
        logger.info("Seeded empty price snapshot to s3://%s/%s", bucket, PRICES_S3_KEY)
    except Exception as exc:  # pragma: no cover - upload failure is non-fatal
        logger.warning("Failed to seed empty price snapshot to S3: %s", exc)


def lambda_handler(event, context):
    """Lambda handler invoked by the scheduler and CDK deploy Trigger.

    Exceptions from ``refresh_prices()`` are caught so that a REQUEST_RESPONSE
    CDK Trigger failure does not roll back the CloudFormation stack.  An empty
    stub is written to S3 on failure to suppress cold-start warnings until the
    next successful scheduled refresh.
    """
    _refresh_failed = False
    try:
        result = refresh_prices()
    except Exception as exc:
        logger.error(
            "Price refresh failed; seeding empty snapshot to suppress cold-start warnings: %s",
            exc,
            exc_info=True,
        )
        try:
            _seed_empty_snapshot()
        except Exception as seed_exc:  # pragma: no cover - defensive; function is designed not to raise
            logger.warning("_seed_empty_snapshot raised unexpectedly: %s", seed_exc)
        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result = {"error": str(exc), "tickers": [], "snapshot": {}, "timestamp": ts}
        _refresh_failed = True

    # Skip the trading agent when prices are unavailable — running it against an
    # empty or stale snapshot could produce incorrect trade signals.
    if (
        not _refresh_failed
        and os.getenv("ALLOTMINT_ENABLE_TRADING_AGENT", "").lower() in {"1", "true", "yes"}
        and trading_agent is not None
    ):
        trading_agent.run()

    return result
