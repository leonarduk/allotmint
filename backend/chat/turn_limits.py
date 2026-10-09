"""Optional limits and audit trail for one tool-calling turn (#10475).

The interactive chat uses neither: it offers every enabled tool and keeps no
record. A background agent (the plan-drift brief) passes a :class:`TurnLimits`
so it can

* offer only an allowlist of tools, and refuse a call to anything else even if
  the model names it anyway,
* cap tool-call round trips and output tokens per completion,
* keep a log of every tool call (arguments and result) to cite as evidence,
* add up the tokens the provider reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AbstractSet, Any, Dict, List, Optional

#: Characters of each tool result kept in :attr:`TurnLimits.tool_log`.
TOOL_LOG_RESULT_CHARS = 4000
#: Characters of JSON-encoded arguments kept before they are truncated.
TOOL_LOG_ARGUMENT_CHARS = 1000


@dataclass
class TurnLimits:
    allowed_tools: Optional[AbstractSet[str]] = None
    max_iterations: Optional[int] = None
    max_tokens: Optional[int] = None
    tool_log: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    def allows(self, name: str) -> bool:
        return self.allowed_tools is None or name in self.allowed_tools

    def record_call(self, name: str, arguments: Any, result: str, is_error: bool) -> None:
        # Arguments are normally small; a huge one is kept as truncated JSON text.
        encoded = json.dumps(arguments, default=str)
        if len(encoded) > TOOL_LOG_ARGUMENT_CHARS:
            arguments = {"truncated_json": encoded[:TOOL_LOG_ARGUMENT_CHARS]}
        self.tool_log.append(
            {
                "tool": name,
                "arguments": arguments,
                "result": result[:TOOL_LOG_RESULT_CHARS],
                "truncated": len(result) > TOOL_LOG_RESULT_CHARS,
                "is_error": is_error,
            }
        )

    def add_usage(self, input_tokens: Any, output_tokens: Any) -> None:
        self.usage["input_tokens"] += int(input_tokens or 0)
        self.usage["output_tokens"] += int(output_tokens or 0)


def not_allowed_message(name: str) -> str:
    return f"{name} is not available to this agent."
