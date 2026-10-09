"""Owner-chosen cash deployment schedules (#10480).

A schedule is the owner's own decision to phase ``total_amount_minor`` (pence)
into one account in ``tranches`` equal parts, one per ``cadence`` period from
``start_date``. The app never proposes a schedule: it only stores what the
owner chose and derives the due dates and tranche amounts from it.

Schedules are kept under the ``cash_deployment`` key of the owner's
``settings.json``, beside the allocation policy and sleeves, so each writer
merges its own key and an unreadable file is never overwritten (see
:mod:`backend.common.settings_file`).
"""

from __future__ import annotations

import calendar
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.common.settings_file import read_settings, settings_path

SETTINGS_KEY = "cash_deployment"
SCHEDULES_KEY = "schedules"
MAX_TRANCHES = 120

Cadence = Literal["weekly", "monthly", "quarterly"]
TargetSource = Literal["plan", "policy"]
ScheduleStatus = Literal["active", "paused", "completed", "cancelled"]

#: Months per period for month-based cadences.
_CADENCE_MONTHS = {"monthly": 1, "quarterly": 3}


class ScheduleNotFoundError(LookupError):
    """No schedule with the requested id exists for the owner."""


class ScheduleInput(BaseModel):
    """The fields an owner chooses when creating or editing a schedule."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account: str = Field(min_length=1)
    total_amount_minor: int = Field(gt=0)
    tranches: int = Field(ge=1, le=MAX_TRANCHES)
    cadence: Cadence = "monthly"
    start_date: date
    target_source: TargetSource = "plan"
    status: ScheduleStatus = "active"

    @field_validator("account")
    @classmethod
    def _plain_account(cls, value: str) -> str:
        if "/" in value or "\\" in value or value.startswith("."):
            raise ValueError("account must be an account id such as 'isa'")
        return value


class DeploymentSchedule(ScheduleInput):
    id: str
    created: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def add_months(start: date, months: int) -> date:
    """``start`` moved by ``months``, clamping the day to the target month's length."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _period_start(schedule: ScheduleInput, index: int) -> date:
    if schedule.cadence == "weekly":
        return schedule.start_date + timedelta(weeks=index)
    return add_months(schedule.start_date, index * _CADENCE_MONTHS[schedule.cadence])


def due_dates(schedule: ScheduleInput) -> list[date]:
    """One due date per tranche, the first on ``start_date``."""
    return [_period_start(schedule, index) for index in range(schedule.tranches)]


def window_end(schedule: ScheduleInput, index: int) -> date:
    """Exclusive end of tranche ``index``'s window: the next tranche's due date (or one period on)."""
    return _period_start(schedule, index + 1)


def tranche_amounts(schedule: ScheduleInput) -> list[int]:
    """Equal tranches in pence; any remainder pence go on the last tranche so they sum exactly."""
    base, remainder = divmod(schedule.total_amount_minor, schedule.tranches)
    amounts = [base] * schedule.tranches
    amounts[-1] += remainder
    return amounts


def _read(owner: str, accounts_root: Optional[Path]) -> tuple[Path, dict[str, Any], list[DeploymentSchedule]]:
    """Settings path, whole settings object and parsed schedules; an unreadable file raises."""
    path = settings_path(owner, accounts_root)
    data = read_settings(path)
    section = data.get(SETTINGS_KEY)
    raw = section.get(SCHEDULES_KEY) if isinstance(section, dict) else None
    schedules = [DeploymentSchedule.model_validate(item) for item in raw if isinstance(item, dict)] if raw else []
    return path, data, schedules


def _write(path: Path, data: dict[str, Any], schedules: list[DeploymentSchedule]) -> None:
    existing = data.get(SETTINGS_KEY)
    section: dict[str, Any] = existing if isinstance(existing, dict) else {}
    data[SETTINGS_KEY] = {**section, SCHEDULES_KEY: [s.to_dict() for s in schedules]}
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def list_schedules(owner: str, accounts_root: Optional[Path] = None) -> list[DeploymentSchedule]:
    return _read(owner, accounts_root)[2]


def get_schedule(owner: str, schedule_id: str, accounts_root: Optional[Path] = None) -> DeploymentSchedule:
    for schedule in list_schedules(owner, accounts_root):
        if schedule.id == schedule_id:
            return schedule
    raise ScheduleNotFoundError(f"No cash deployment schedule {schedule_id!r}")


def create_schedule(owner: str, body: ScheduleInput, accounts_root: Optional[Path] = None) -> DeploymentSchedule:
    path, data, schedules = _read(owner, accounts_root)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    schedule = DeploymentSchedule(**body.model_dump(), id=uuid.uuid4().hex[:12], created=created)
    _write(path, data, [*schedules, schedule])
    return schedule


def update_schedule(
    owner: str, schedule_id: str, body: ScheduleInput, accounts_root: Optional[Path] = None
) -> DeploymentSchedule:
    path, data, schedules = _read(owner, accounts_root)
    for index, existing in enumerate(schedules):
        if existing.id == schedule_id:
            updated = DeploymentSchedule(**body.model_dump(), id=existing.id, created=existing.created)
            schedules[index] = updated
            _write(path, data, schedules)
            return updated
    raise ScheduleNotFoundError(f"No cash deployment schedule {schedule_id!r}")


def delete_schedule(owner: str, schedule_id: str, accounts_root: Optional[Path] = None) -> None:
    path, data, schedules = _read(owner, accounts_root)
    kept = [s for s in schedules if s.id != schedule_id]
    if len(kept) == len(schedules):
        raise ScheduleNotFoundError(f"No cash deployment schedule {schedule_id!r}")
    _write(path, data, kept)
