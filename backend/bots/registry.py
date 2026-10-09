"""Bot registry: the shared interface for scheduled jobs and AI agents (#10477).

A *bot* is any automated job the app runs: the existing scheduled Lambdas
(price refresh, dividend refresh, pension report, trading agent) and the AI
agents that register here as they land (#10471, #10474, #10475, #10476).

Each bot declares who it is (``id``, ``name``, ``description``, ``kind``,
``scope``), a Pydantic ``settings_model`` (always a :class:`BotSettings`
subclass, so ``enabled`` and ``cadence`` are common to all), the schedule its
EventBridge rule fires on, and a ``run(context, settings)`` method returning a
:class:`RunResult`. The runner (:mod:`backend.bots.runner`) owns run records,
the in-progress guard and the enabled/due checks, so a bot's ``run`` only does
its own work.

Settings models must contain public, non-secret values only: they are served
verbatim (with their JSON schema) by ``GET /bots/{id}`` and edited on the Bots
page. Provider API keys and other secrets stay in server config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

BotKind = Literal["ai", "rules", "job"]
BotScope = Literal["system", "owner"]
Cadence = Literal["daily", "weekly", "monthly"]
RunStatus = Literal["running", "ok", "failed", "partial", "skipped"]
RunTrigger = Literal["schedule", "manual", "invoke", "event"]

_BOT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class BotSettings(BaseModel):
    """Settings every bot has. Bots subclass this to add their own fields.

    ``cadence`` can only make a bot run *less* often than its schedule fires:
    a weekly bot on a daily rule runs on the first firing at least ~a week
    after its last run and records a "skipped" run on the others.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    cadence: Cadence = "daily"


@dataclass(frozen=True)
class Schedule:
    """A UTC cron-like schedule mirroring the bot's EventBridge rule.

    ``weekday`` is 0=Monday..6=Sunday; ``day`` is the day of the month. Leave
    both unset for a daily rule.
    """

    hour: int
    minute: int = 0
    weekday: Optional[int] = None
    day: Optional[int] = None

    @property
    def description(self) -> str:
        at = f"{self.hour:02d}:{self.minute:02d} UTC"
        if self.day is not None:
            return f"Monthly on day {self.day} at {at}"
        if self.weekday is not None:
            return f"Weekly on {_WEEKDAYS[self.weekday]} at {at}"
        return f"Daily at {at}"

    def _matches_day(self, moment: datetime) -> bool:
        if self.day is not None:
            return moment.day == self.day
        if self.weekday is not None:
            return moment.weekday() == self.weekday
        return True

    def fire_times_after(self, now: datetime) -> Iterator[datetime]:
        """Yield the rule's firing times strictly after ``now``, in order."""

        now = now.astimezone(timezone.utc)
        candidate = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        # Bounded so a malformed schedule (e.g. day=31 in a short month) can
        # never loop forever; 400 days covers a full year of monthly firings.
        for _ in range(400):
            if self._matches_day(candidate):
                yield candidate
            candidate += timedelta(days=1)


@dataclass
class BotRunContext:
    """What a bot's ``run`` gets to know about the run it is part of."""

    run_id: str
    bot_id: str
    trigger: RunTrigger
    started_at: datetime
    actor: Optional[str] = None
    owner: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Outcome of one run. ``raw`` is returned to the caller, never stored."""

    status: RunStatus
    summary: str = ""
    report: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    owner: Optional[str] = None
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    raw: Any = None


@runtime_checkable
class Bot(Protocol):
    """The interface every bot implements. See the module docstring."""

    id: str
    name: str
    description: str
    kind: BotKind
    scope: BotScope
    settings_model: type[BotSettings]

    @property
    def default_schedule(self) -> Optional[Schedule]:
        """The EventBridge rule's schedule; ``None`` for event-driven bots."""

    #: A ``running`` record older than this is treated as stale (crashed run).
    timeout_minutes: int

    def default_settings(self) -> Dict[str, Any]:
        """Settings to use before anything is stored (current config values)."""

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        """Do the work. May raise: the runner records the failure."""


_REGISTRY: Dict[str, Bot] = {}
_loaded = False


def register_bot(bot: Bot, *, replace: bool = False) -> Bot:
    """Add ``bot`` to the registry. Returns it so it can decorate an instance."""

    if not _BOT_ID.match(bot.id):
        raise ValueError(f"Invalid bot id {bot.id!r}: use lower-case letters, digits and dashes")
    if not issubclass(bot.settings_model, BotSettings):
        raise TypeError(f"{bot.id}: settings_model must subclass BotSettings")
    if bot.id in _REGISTRY and not replace:
        raise ValueError(f"Bot {bot.id!r} is already registered")
    _REGISTRY[bot.id] = bot
    return bot


def unregister_bot(bot_id: str) -> None:
    """Remove a bot (tests only)."""

    _REGISTRY.pop(bot_id, None)


def _ensure_loaded() -> None:
    """Import the built-in adapters once, on first registry access.

    Deferred so importing :mod:`backend.bots` (e.g. from the trading agent's
    settings lookup) does not import every job module.
    """

    global _loaded
    if _loaded:
        return
    _loaded = True
    from backend.bots import adapters  # noqa: F401  (registers on import)


def is_valid_bot_id(bot_id: str) -> bool:
    return bool(_BOT_ID.match(bot_id))


def get_bot(bot_id: str) -> Bot:
    """Return the registered bot or raise ``KeyError``."""

    _ensure_loaded()
    return _REGISTRY[bot_id]


def list_bots() -> List[Bot]:
    _ensure_loaded()
    return list(_REGISTRY.values())


__all__ = [
    "Bot",
    "BotKind",
    "BotRunContext",
    "BotScope",
    "BotSettings",
    "Cadence",
    "RunResult",
    "RunStatus",
    "RunTrigger",
    "Schedule",
    "get_bot",
    "is_valid_bot_id",
    "list_bots",
    "register_bot",
    "unregister_bot",
]
