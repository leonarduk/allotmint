"""The allowance guardian's no-advice wording check (#10479, #10491).

Imperative or recommending phrases that guardian output must never contain.
The deterministic report's tests and the LLM explainer
(:mod:`backend.allowance_guardian.agent`) use the same list, so a model reply
is held to the same standard as the report's own text.

It lives outside ``backend/allowance_guardian`` because the guardian's tests
scan every string literal in that package for these phrases, and the patterns
themselves would match.
"""

from __future__ import annotations

import re
from typing import List

ADVICE_PATTERNS: List[str] = [
    r"\byou should\b",
    r"\bshould (?:you )?(?:contribute|pay|use|increase|reduce|consider)\b",
    r"\b(?:we )?recommend",
    r"\bconsider (?:using|paying|contributing|increasing|reducing)\b",
    r"\buse (?:your )?carry[- ]forward\b",
    r"\bcontribute (?:£|up to|more|less|another)",
    r"\b(?:increase|reduce|top up|stop|pause) your\b",
    r"\bbest to\b",
    r"\bmake sure\b",
]


def advice_phrases(text: str) -> List[str]:
    """The patterns in :data:`ADVICE_PATTERNS` that ``text`` matches (empty when factual)."""
    return [pattern for pattern in ADVICE_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE)]
