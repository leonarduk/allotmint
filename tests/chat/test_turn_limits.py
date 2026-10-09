"""TurnLimits bookkeeping (#10475)."""

from backend.chat.turn_limits import TOOL_LOG_ARGUMENT_CHARS, TOOL_LOG_RESULT_CHARS, TurnLimits


def test_record_call_truncates_large_arguments_and_results():
    limits = TurnLimits()
    limits.record_call("get_live_prices", {"tickers": ["X.L"] * 1000}, "r" * (TOOL_LOG_RESULT_CHARS + 5), False)
    [call] = limits.tool_log
    assert set(call["arguments"]) == {"truncated_json"}
    assert len(call["arguments"]["truncated_json"]) == TOOL_LOG_ARGUMENT_CHARS
    assert len(call["result"]) == TOOL_LOG_RESULT_CHARS and call["truncated"] is True


def test_record_call_keeps_small_arguments_as_given():
    limits = TurnLimits(allowed_tools={"a"})
    limits.record_call("a", {"series": ["bank_rate"]}, "ok", False)
    assert limits.tool_log[0]["arguments"] == {"series": ["bank_rate"]}
    assert limits.allows("a") and not limits.allows("b")
