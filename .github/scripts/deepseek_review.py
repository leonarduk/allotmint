"""DeepSeek AI code review script called by deepseek-pr-review.yml.

DeepSeek provides an OpenAI-compatible chat completions API at
https://api.deepseek.com/v1/chat/completions. The integration reuses the
shared `review_common` helpers so the prompt, verdict format, and error
handling stay identical across all three reviewers.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from review_common import (
    build_prompt,
    emit_empty_diff_notice,
    fetch_review,
    finalize_review,
    load_review_context,
)

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TOKENS = 4096


def get_deepseek_model() -> str:
    """Return the DeepSeek model ID to call for advisory reviews.

    Defaults to `deepseek-v4-flash` (the latest DeepSeek-V3 alias). Set
    `DEEPSEEK_MODEL` to override (e.g. to `deepseek-reasoner` for a deeper
    review). An unset or empty value falls back to the default.
    """
    return os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL


def get_max_tokens() -> int:
    """Return the max_tokens budget for DeepSeek review responses."""
    raw = os.environ.get("DEEPSEEK_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_TOKENS
    return max(256, value)


def extract_deepseek_review(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract review text from DeepSeek chat-completions responses.

    DeepSeek's API is OpenAI-compatible: the response shape is always
    `{"choices": [{"message": {"content": "<string>"}}]}` — unlike Anthropic's
    content-block format, DeepSeek never returns `content` as a list, so no
    list-handling branch is needed here.

    Thinking-capable models (e.g. `deepseek-v4-flash`, `deepseek-reasoner`)
    also return a `reasoning_content` field holding the chain-of-thought. If
    `max_tokens` is exhausted before the model finishes reasoning, `content`
    comes back empty even though the response itself is large — this used to
    fail with no clue why (#5697). `fetch_deepseek_review` disables thinking
    mode to avoid this, but if a response still comes back with reasoning and
    no content, surface that explicitly instead of a bare empty-review error.
    """
    choices = data.get("choices", [])
    if not choices:
        return "", {}

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "")
    review = content.strip() if isinstance(content, str) else ""

    if not review:
        reasoning = message.get("reasoning_content") or ""
        finish_reason = choice.get("finish_reason")
        if reasoning:
            print(
                "WARNING: DeepSeek response contained only reasoning_content "
                f"({len(reasoning)} chars, finish_reason={finish_reason!r}) and no "
                "final content — the model likely ran out of max_tokens while "
                "thinking. Consider raising DEEPSEEK_MAX_TOKENS.",
                file=sys.stderr,
            )

    return review, {}


def fetch_deepseek_review(api_key: str, prompt: str) -> str:
    """Call DeepSeek and return the advisory review body.

    The workflow is expected to provide `DEEPSEEK_API_KEY`; HTTP errors are
    surfaced with a non-zero exit code so the advisory workflow can post a
    skip/failure notice instead of silently succeeding.
    """
    model = get_deepseek_model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": get_max_tokens(),
        "temperature": 0.2,
    }
    if model != "deepseek-reasoner":
        # Thinking-capable models (the default deepseek-v4-flash) default to
        # thinking mode "on" with high effort, which can burn the entire
        # max_tokens budget on reasoning_content and leave `content` empty
        # (see #5697 — reviews were failing with a 200 response and no visible
        # reason). PR review is a straightforward advisory task that doesn't
        # need chain-of-thought, so disable it for a reliable final answer
        # within budget. Skip this for deepseek-reasoner (opted into via the
        # "Deep Review Required" label with a larger token budget) since
        # reasoning is that model's whole purpose and disabling isn't
        # documented as supported for it.
        payload["thinking"] = {"type": "disabled"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    review, _extra = fetch_review(
        "https://api.deepseek.com/v1/chat/completions",
        headers,
        payload,
        extract_deepseek_review,
        "DeepSeek",
    )
    return review


def main() -> int:
    """Run the advisory DeepSeek review flow."""
    context = load_review_context("DEEPSEEK_API_KEY")
    if not context.diff.strip():
        return emit_empty_diff_notice("DeepSeek")

    prompt = build_prompt(
        context.pr_title,
        context.diff,
        context.issue_body,
        context.discussion,
        context.verified_facts,
    )
    review = fetch_deepseek_review(context.api_key, prompt)
    return finalize_review(review, "ERROR: DeepSeek API returned an empty review")


if __name__ == "__main__":
    raise SystemExit(main())
