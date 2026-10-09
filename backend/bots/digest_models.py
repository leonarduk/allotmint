"""The bots digest item contract (#10485).

Every bot's run result carries ``digest_items``: a list of :class:`DigestItem`
dicts describing what the run found that may need the owner. The digest
composer (``backend.bots.digest``) only ever restates these items; it never
adds facts of its own.

``dedupe_key`` identifies "the same finding" across runs so the composer can
tell a **new** item from one that is **still open**, and notice when a
previously open item has been **resolved** (its key no longer appears).

``owner`` is the owner the item is about, or ``None`` for a system-wide item
(e.g. a failed scheduled job), which only admins see.

Until the bot registry (#10477) lands, run records are read through the small
:class:`RunRecordSource` interface in ``backend.bots.run_records``; the
registry can implement that interface and nothing here needs to change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# Lower rank sorts first.
SEVERITY_RANK: Dict[Severity, int] = {
    Severity.HIGH: 0,
    Severity.MEDIUM: 1,
    Severity.LOW: 2,
    Severity.INFO: 3,
}

ItemStatus = Literal["new", "still_open", "resolved"]
RunStatus = Literal["ok", "failed", "partial", "skipped"]
BotKind = Literal["ai", "rules", "job"]
BotScope = Literal["owner", "system"]
BotState = Literal["ok", "failed", "partial", "skipped", "not_run_yet"]
DigestPeriod = Literal["weekly", "monthly"]


def _as_utc(value: datetime) -> datetime:
    """Treat naive timestamps as UTC so items from different bots always compare."""

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class DigestItem(BaseModel):
    """One finding a bot reports for the digest. Bots emit these in ``digest_items``."""

    id: str
    bot: str
    owner: Optional[str] = None
    severity: Severity = Severity.INFO
    title: str
    summary: str = ""
    link: Optional[str] = None
    action_required: bool = False
    created: UtcDatetime
    dedupe_key: str


class DigestEntry(DigestItem):
    """A :class:`DigestItem` as it appears in a composed digest."""

    status: ItemStatus


class BotDescriptor(BaseModel):
    """What the digest needs to know about a bot (a subset of the #10477 ``Bot`` protocol)."""

    id: str
    name: str
    kind: BotKind = "job"
    scope: BotScope = "owner"


class BotRunRecord(BaseModel):
    """The parts of a stored run record (#10477 ``runs.py``) that the digest reads."""

    bot_id: str
    status: RunStatus
    started_at: UtcDatetime
    finished_at: Optional[UtcDatetime] = None
    summary: str = ""
    error: Optional[str] = None
    digest_items: List[DigestItem] = Field(default_factory=list)


class BotStatus(BaseModel):
    """Per-bot line in the digest: last run state, or ``not_run_yet``."""

    bot: str
    name: str
    state: BotState
    last_run_at: Optional[UtcDatetime] = None
    summary: str = ""


class Digest(BaseModel):
    """A composed digest for one owner, as stored and served."""

    owner: str
    period: DigestPeriod = "weekly"
    generated_at: UtcDatetime
    opener: str
    items: List[DigestEntry] = Field(default_factory=list)
    resolved: List[DigestEntry] = Field(default_factory=list)
    bots: List[BotStatus] = Field(default_factory=list)
    # Items dropped by the per-bot cap, by bot id, so nothing is silently hidden.
    truncated: Dict[str, int] = Field(default_factory=dict)
    # Every open dedupe_key, including capped ones, so a capped item is not
    # reported as "new" again in the next digest.
    open_keys: List[str] = Field(default_factory=list)

    @property
    def needs_owner(self) -> bool:
        return bool(self.items)


__all__ = [
    "SEVERITY_RANK",
    "BotDescriptor",
    "BotKind",
    "BotRunRecord",
    "BotScope",
    "BotState",
    "BotStatus",
    "Digest",
    "DigestEntry",
    "DigestItem",
    "DigestPeriod",
    "ItemStatus",
    "RunStatus",
    "Severity",
]
