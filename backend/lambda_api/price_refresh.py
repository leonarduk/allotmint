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
``refresh_prices()``, logs the error, writes an empty stub snapshot (only when
no snapshot exists yet, so a good one is never replaced with ``{}``, #8805) so
the "price snapshot not yet seeded" CloudWatch warning is suppressed on
subsequent cold starts, and returns normally.

Bot run records
---------------
The handler runs through the bot runner (``backend.bots``, #10477), which
records every run on the Bots page and skips a scheduled firing when the bot
is disabled there. Direct invocations (the deploy Trigger, the CI warm-up)
always run. The return value is still ``refresh_prices()``'s result.

System-job context
------------------
The handler runs inside :func:`backend.auth.system_job_context`: it has no
request user, and with auth enabled owner discovery would otherwise hide every
owner, leaving the refresh with no tickers (#8805).  Real prices will be populated on the next
scheduled EventBridge invocation.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event
from backend.common.portfolio_utils import DATA_BUCKET_ENV, PRICES_S3_KEY
from backend.common.prices import put_empty_snapshot_if_absent, refresh_prices
from backend.config import config
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

try:  # trading agent is optional; skip if missing
    import trading_agent  # type: ignore
except Exception:  # pragma: no cover - only hit when package missing
    trading_agent = None

logger = logging.getLogger(__name__)


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

        # Only seed a missing key, atomically: a failed refresh must not replace
        # the last good snapshot with {} (#8805), but a missing key must still
        # be created for the post-deploy check (#3685).
        if not put_empty_snapshot_if_absent(boto3.client("s3"), bucket):
            logger.info("Price snapshot already present; not seeding {}")
            return
        logger.info(
            "Seeded empty price snapshot to s3://%s/%s", sanitise_log_value(bucket), sanitise_log_value(PRICES_S3_KEY)
        )
    except Exception as exc:
        # Non-fatal, but anything other than "key exists" means the key may be
        # missing and the post-deploy snapshot check will fail (#3685, #8943).
        logger.error("Failed to seed empty price snapshot to S3; the key may not exist: %s", sanitise_log_value(exc))


def lambda_handler(event, context):
    """Lambda handler invoked by the scheduler and CDK deploy Trigger.

    Exceptions from ``refresh_prices()`` are caught so that a REQUEST_RESPONSE
    CDK Trigger failure does not roll back the CloudFormation stack.  An empty
    stub is written to S3 on failure, if no snapshot exists yet, to suppress
    cold-start warnings until the next successful scheduled refresh.
    """
    # The scheduled refresh has no request user; run it as a trusted system job
    # so owner discovery returns every owner even with auth enabled (#8805).
    with system_job_context():
        return handle_lambda_event("price-refresh", event)


def _run_refresh():
    _refresh_failed = False
    try:
        result = refresh_prices()
    except Exception as exc:
        logger.error(
            "Price refresh failed; seeding empty snapshot to suppress cold-start warnings: %s; traceback: %s",
            sanitise_log_value(exc),
            sanitise_exception_traceback(exc),
        )
        try:
            _seed_empty_snapshot()
        except Exception as seed_exc:  # pragma: no cover - defensive; function is designed not to raise
            logger.warning("_seed_empty_snapshot raised unexpectedly: %s", sanitise_log_value(seed_exc))
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
