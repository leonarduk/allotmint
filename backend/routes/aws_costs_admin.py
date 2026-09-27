"""Admin endpoint reporting AWS costs broken down by service.

Wraps the AWS Cost Explorer ``GetCostAndUsage`` API, grouped by ``SERVICE``,
so the owner can see what the deployed infrastructure actually costs and
which service is driving spend (issue #8016).

Cost Explorer is billed per API call and is a global (us-east-1-only)
service, so results are cached for :data:`_CACHE_TTL_SECONDS` rather than
calling the API on every request, and the client is pinned to ``us-east-1``
regardless of the Lambda's own deployment region.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query

from backend.common.ttl_cache import TTLCache

router = APIRouter(prefix="/admin/aws-costs", tags=["aws-costs-admin"])

# Cost Explorer data is finalized well behind real time and is billed per
# request; an hourly cache keeps this endpoint cheap to poll from a dashboard
# without hiding same-day cost changes for long.
_CACHE_TTL_SECONDS = 60 * 60
_cache: TTLCache[dict[str, Any]] = TTLCache(_CACHE_TTL_SECONDS, name="aws_costs_admin")

# Cost Explorer's API endpoint only exists in us-east-1, independent of which
# region the rest of the stack is deployed to.
_COST_EXPLORER_REGION = "us-east-1"


def _default_period() -> tuple[str, str]:
    """Return (start, end) covering month-to-date, as Cost Explorer expects.

    ``End`` is exclusive and must be strictly after ``Start`` and no later
    than tomorrow, so "today" alone (e.g. on the 1st of the month) would be
    rejected; using tomorrow as the exclusive end always satisfies both.
    """

    today = dt.date.today()
    start = today.replace(day=1)
    end = today + dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _fetch_cost_by_service(start: str, end: str) -> dict[str, Any]:
    client = boto3.client("ce", region_name=_COST_EXPLORER_REGION)
    try:
        response = client.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
    except (ClientError, BotoCoreError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    totals: dict[str, float] = {}
    unit = "USD"
    for period in response.get("ResultsByTime", []):
        for group in period.get("Groups", []):
            keys = group.get("Keys") or []
            service = keys[0] if keys else "Unknown"
            metric = group.get("Metrics", {}).get("UnblendedCost", {})
            amount = float(metric.get("Amount", 0.0))
            unit = metric.get("Unit", unit)
            totals[service] = totals.get(service, 0.0) + amount

    services = [
        {"service": service, "amount": round(amount, 2), "unit": unit}
        for service, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]
    total_amount = round(sum(totals.values()), 2)

    return {
        "start": start,
        "end": end,
        "total": {"amount": total_amount, "unit": unit},
        "services": services,
    }


@router.get("")
def get_aws_costs_by_service(
    start: str | None = Query(None, description="Inclusive start date (YYYY-MM-DD); defaults to month-to-date"),
    end: str | None = Query(None, description="Exclusive end date (YYYY-MM-DD); defaults to tomorrow"),
) -> dict[str, Any]:
    """Return AWS costs for ``[start, end)`` grouped by service, plus a total."""

    default_start, default_end = _default_period()
    period_start = start or default_start
    period_end = end or default_end
    if period_end <= period_start:
        raise HTTPException(status_code=400, detail="end must be after start")

    return _cache.get_or_build(
        (period_start, period_end),
        lambda: _fetch_cost_by_service(period_start, period_end),
    )
