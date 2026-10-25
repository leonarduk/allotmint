import logging

import pytest

from backend.chat.plan_guard import PLAN_REMINDER, PLAN_TOOL_NAME, PlanGuard, is_plan_question


@pytest.mark.parametrize(
    "message",
    [
        "How far is steve's allocation from a Golden Butterfly mix?",
        "Has my portfolio drifted?",
        "Should I rebalance?",
        "Am I on track?",
        "Compare me with a 60/40 portfolio",
        "What's my target allocation?",
        "How does it compare with the All Weather portfolio?",
        "Show me the investment plan",
        "How far am I from my target allocation?",
        "How far is my allocation from my plan?",
        "How far off am I from the model weights?",
    ],
)
def test_flags_allocation_vs_target_questions(message):
    assert is_plan_question(message)


@pytest.mark.parametrize(
    "message",
    [
        "What's VOD.L trading at?",
        "List the owners",
        "Export my trades as a spreadsheet",
        "",
        "hi",
        # Price-level "how far ... from" questions are not about the plan (#11083).
        "How far is VOD.L from its 52-week low?",
        "How far is my portfolio from its all-time high?",
    ],
)
def test_ignores_unrelated_questions(message):
    assert not is_plan_question(message)


def test_reminds_once_when_the_plan_tool_was_offered_but_not_called(caplog):
    guard = PlanGuard("drift?", ["get_allocation", PLAN_TOOL_NAME])

    with caplog.at_level(logging.INFO, logger="backend.chat.plan_guard"):
        assert guard.reminder(iterations_left=3) == PLAN_REMINDER
        assert guard.reminder(iterations_left=2) is None

    records = [r for r in caplog.records if getattr(r, "event", None) == "chat.plan_guard"]
    assert [(r.tool, r.levelname) for r in records] == [(PLAN_TOOL_NAME, "INFO")]


def test_no_reminder_once_the_plan_tool_was_called():
    guard = PlanGuard("drift?", [PLAN_TOOL_NAME])
    guard.saw_call("get_allocation")
    guard.saw_call(PLAN_TOOL_NAME)
    assert guard.reminder(iterations_left=3) is None


def test_no_reminder_when_the_plan_tool_is_not_offered():
    assert PlanGuard("drift?", ["get_allocation"]).reminder(iterations_left=3) is None


def test_no_reminder_for_unrelated_questions():
    assert PlanGuard("what's VOD.L at?", [PLAN_TOOL_NAME]).reminder(iterations_left=3) is None


def test_no_reminder_at_the_iteration_cap():
    guard = PlanGuard("drift?", [PLAN_TOOL_NAME])
    assert guard.reminder(iterations_left=0) is None
