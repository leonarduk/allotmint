"""Analytics event ingestion and funnel summaries."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import get_current_user, oauth2_scheme
from backend.common.analytics_store import AnalyticsEvent, append_event, load_events
from backend.config import config

router = APIRouter(prefix="/analytics", tags=["analytics"])

_ALLOWED_EVENTS: Dict[str, set[str]] = {
    "trail": {"view", "task_started", "task_completed"},
    "virtual_portfolio": {"view", "create", "update", "delete", "select"},
}

_FUNNEL_STEPS: Dict[str, list[str]] = {
    "trail": ["view", "task_started", "task_completed"],
    "virtual_portfolio": ["view", "create", "update", "delete"],
}


class AnalyticsEventIn(BaseModel):
    """Inbound analytics payload."""

    source: str = Field(..., description="Feature emitting the event", pattern=r"^[a-z_]+$")
    event: str = Field(..., description="Event name", min_length=1, max_length=64)
    user: Optional[str] = Field(
        default=None,
        description="Optional user identifier overriding the authenticated user",
        max_length=128,
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary JSON metadata captured with the event",
    )
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp for the event (defaults to request time)",
    )


class FunnelStep(BaseModel):
    event: str
    count: int


class FunnelSummary(BaseModel):
    source: str
    total_events: int
    unique_users: int
    first_event_at: Optional[datetime]
    last_event_at: Optional[datetime]
    steps: list[FunnelStep]
    other_events: Dict[str, int] | None = None


def _validate_event(payload: AnalyticsEventIn) -> None:
    allowed = _ALLOWED_EVENTS.get(payload.source)
    if not allowed:
        raise HTTPException(status_code=400, detail="Unknown analytics source")
    if payload.event not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported event for source")


async def _optional_current_user(request: Request) -> Optional[str]:
    if config.disable_auth:
        return None
    token = await oauth2_scheme(request)
    return await get_current_user(token)


@router.post("/events", status_code=200)
async def log_event(
    payload: AnalyticsEventIn,
    current_user: Optional[str] = Depends(_optional_current_user),
) -> Dict[str, str]:
    """Store an analytics event for later funnel analysis."""

    _validate_event(payload)
    occurred_at = payload.occurred_at or datetime.now(timezone.utc)
    user = payload.user
    if user is None and config.disable_auth is not True:
        user = current_user

    try:
        metadata = payload.metadata
        if metadata is not None:
            # Ensure metadata is JSON serialisable – json.dumps raises TypeError otherwise.
            json.dumps(metadata)
    except TypeError as exc:  # pragma: no cover - defensive, unlikely in tests
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {exc}") from exc

    append_event(
        AnalyticsEvent(
            source=payload.source,
            event=payload.event,
            user=user,
            occurred_at=occurred_at,
            metadata=metadata,
        )
    )
    return {"status": "ok"}


@router.get("/funnels/{source}", response_model=FunnelSummary)
async def get_funnel(source: str) -> FunnelSummary:
    """Return a simple funnel summary for ``source``."""

    if source not in _FUNNEL_STEPS:
        raise HTTPException(status_code=404, detail="Unknown analytics source")

    events = load_events(source)
    if not events:
        return FunnelSummary(
            source=source,
            total_events=0,
            unique_users=0,
            first_event_at=None,
            last_event_at=None,
            steps=[FunnelStep(event=evt, count=0) for evt in _FUNNEL_STEPS[source]],
            other_events=None,
        )

    counts = Counter(evt.event for evt in events)
    users = {evt.user for evt in events if evt.user}
    first = min(evt.occurred_at for evt in events)
    last = max(evt.occurred_at for evt in events)
    funnel_steps = [FunnelStep(event=step, count=counts.get(step, 0)) for step in _FUNNEL_STEPS[source]]
    other_events = {
        name: count
        for name, count in counts.items()
        if name not in _FUNNEL_STEPS[source]
    }

    return FunnelSummary(
        source=source,
        total_events=sum(counts.values()),
        unique_users=len(users),
        first_event_at=first,
        last_event_at=last,
        steps=funnel_steps,
        other_events=other_events or None,
    )

