"""Expected contribution schedule per owner (#10479).

An owner records what they expect to be paid into each pension or ISA account:
amount (pence), frequency, source and expected day of month. The guardian reads
the schedule to check arrivals (:mod:`backend.allowance_guardian.match`) and to
project the annual allowance to the tax year end
(:mod:`backend.allowance_guardian.projection`). The guardian itself never writes
it; only the owner does, through ``PUT /allowance-guardian/{owner}/schedule``.

Stored at ``<data_root>/contribution_schedules/<owner>.json``.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Iterator, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.common.path_utils import safe_join

SCHEDULES_DIRNAME = "contribution_schedules"

# Same owner-id shape as backend/common/investment_plan.py; safe_join guards traversal.
_OWNER_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,64}$")

Frequency = Literal["monthly", "quarterly", "annual"]
# personal_relief_at_source: the owner pays the net amount and the provider claims
#   basic-rate relief later, so the allowance counts amount / 0.8.
# personal_gross: a personal contribution with no relief added at source.
# employer: an employer or salary-sacrifice contribution (counts at face value).
# isa_subscription: money into an ISA; counts towards the ISA limit, not the pension one.
Source = Literal["personal_relief_at_source", "personal_gross", "employer", "isa_subscription"]

_MONTH_STEP = {"monthly": 1, "quarterly": 3, "annual": 12}

# Basic-rate relief at source: the provider adds 25% of the net payment (20% of gross).
RELIEF_AT_SOURCE_GROSS_UP_NUM = 5
RELIEF_AT_SOURCE_GROSS_UP_DEN = 4


class ScheduledContribution(BaseModel):
    """One recurring contribution the owner expects to see in ``account``."""

    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=1, max_length=64)
    amount_minor: int = Field(gt=0, description="Amount paid in, in pence (net of relief at source).")
    frequency: Frequency = "monthly"
    source: Source
    expected_day: int = Field(ge=1, le=31)
    start_date: date
    end_date: Optional[date] = None
    label: Optional[str] = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _check(self) -> "ScheduledContribution":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        is_isa = self.source == "isa_subscription"
        if is_isa != is_isa_account(self.account):
            raise ValueError("isa_subscription is for ISA accounts only, and ISA accounts take only that source")
        return self

    @property
    def is_pension(self) -> bool:
        return self.source != "isa_subscription"

    def allowance_minor(self) -> int:
        """Pence this contribution uses of its annual allowance (gross for relief at source)."""
        if self.source == "personal_relief_at_source":
            return self.amount_minor * RELIEF_AT_SOURCE_GROSS_UP_NUM // RELIEF_AT_SOURCE_GROSS_UP_DEN
        return self.amount_minor


class ContributionSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    contributions: List[ScheduledContribution] = Field(default_factory=list, max_length=50)


def is_isa_account(account: str) -> bool:
    return "isa" in (account or "").lower()


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def expected_dates(item: ScheduledContribution, start: date, end: date) -> Iterator[date]:
    """Dates ``item`` is expected in ``[start, end]``, the day clamped to short months (31 -> 30 Apr)."""
    step = _MONTH_STEP[item.frequency]
    year, month = item.start_date.year, item.start_date.month
    last = min(end, item.end_date) if item.end_date else end
    while True:
        due = _clamped(year, month, item.expected_day)
        if due > last:
            return
        if due >= max(start, item.start_date):
            yield due
        month += step
        year, month = year + (month - 1) // 12, (month - 1) % 12 + 1


def schedules_dir(data_root: Path) -> Path:
    return Path(data_root) / SCHEDULES_DIRNAME


def _schedule_path(owner: str, data_root: Path) -> Path:
    if not _OWNER_RE.match(owner or ""):
        raise ValueError(f"Invalid owner id {owner!r}")
    return safe_join(schedules_dir(data_root), f"{owner}.json")


def parse_schedule(data: object, owner: str) -> ContributionSchedule:
    """Validate ``data`` as ``owner``'s schedule; raises ``pydantic.ValidationError``/``ValueError``."""
    schedule = ContributionSchedule.model_validate(data)
    if schedule.owner != owner:
        raise ValueError(f"Schedule owner {schedule.owner!r} does not match {owner!r}")
    return schedule


def load_schedule(owner: str, data_root: Path) -> ContributionSchedule:
    """``owner``'s saved schedule, or an empty one when none has been saved."""
    path = _schedule_path(owner, data_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ContributionSchedule(owner=owner)
    return parse_schedule(raw, owner)


def save_schedule(schedule: ContributionSchedule, data_root: Path) -> Path:
    """Write ``schedule`` atomically to ``<data_root>/contribution_schedules/<owner>.json``."""
    path = _schedule_path(schedule.owner, data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(schedule.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{schedule.owner}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
