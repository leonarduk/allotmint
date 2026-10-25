"""Make sure a chat turn about allocation/drift/targets consults the owner's plan.

``INVESTMENT_PLAN_GUIDANCE`` in :mod:`backend.chat.local_tools` asks the model to
call ``get_investment_plan`` before answering such questions, but tool choice is
still the model's, and the same drift question in two fresh chats could come
back with contradictory claims about whether the owner has a plan (#10613).

:class:`PlanGuard` is the deterministic backstop (#10653): when the user's
message looks like an allocation-vs-target question, ``get_investment_plan`` was
offered this turn, and the model is about to answer without having called it,
the agent loop sends one reminder and runs one more iteration. It fires at most
once per turn and never past the loop's iteration cap. Keyword matching only, so
it adds no extra model call for unrelated questions.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

PLAN_TOOL_NAME = "get_investment_plan"

_PLAN_QUESTION = re.compile(
    r"\bdrift"
    r"|\brebalanc"
    r"|\b(?:on|off)[ -]track\b"
    r"|\btarget (?:allocation|mix|weights?|split|portfolio)s?\b"
    r"|\b(?:my|our|his|her|their|the) targets?\b"
    r"|\b(?:60/40|70/30|80/20|50/50|40/60)\b"
    r"|\bgolden butterfly\b"
    r"|\ball[ -]weather\b"
    r"|\bpermanent portfolio\b"
    r"|\bmodel (?:mix|portfolio)\b"
    r"|\binvestment plan\b"
    r"|\bhow far\b.*\bfrom\b",
    re.IGNORECASE | re.DOTALL,
)

PLAN_REMINDER = (
    f"Before answering, call {PLAN_TOOL_NAME} for the owner this question is about "
    "and base the answer on its result. If that call fails or is refused, say the "
    "plan could not be read; do not say that no plan is recorded."
)


def is_plan_question(message: str) -> bool:
    """True when ``message`` asks about allocation against a target, drift or rebalancing."""

    return bool(_PLAN_QUESTION.search(message or ""))


class PlanGuard:
    """Tracks one turn: is a plan-consulting reminder still owed?"""

    def __init__(self, message: str, offered_tool_names: Iterable[str]) -> None:
        self._pending = PLAN_TOOL_NAME in set(offered_tool_names) and is_plan_question(message)

    def saw_call(self, name: str) -> None:
        """Record a tool call the model made; any attempt at the plan tool settles it."""

        if name == PLAN_TOOL_NAME:
            self._pending = False

    def reminder(self, iterations_left: int) -> Optional[str]:
        """The reminder to send before accepting a final answer, or ``None``.

        ``iterations_left`` is how many more model completions the loop allows;
        with none left the answer stands rather than breaching the cap.
        """

        if not self._pending or iterations_left < 1:
            return None
        self._pending = False
        # Tool name only, never arguments or results (#10613).
        logger.info(
            "chat.plan_guard reminding the model to call %s",
            sanitise_log_value(PLAN_TOOL_NAME),
            extra={"event": "chat.plan_guard", "tool": PLAN_TOOL_NAME},
        )
        return PLAN_REMINDER
