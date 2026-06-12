"""Claude AI code review script called by claude-pr-review.yml."""

from __future__ import annotations

import os
from typing import Any

from review_common import build_prompt, emit_empty_diff_notice, fetch_review, finalize_review, load_review_context

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 2500


def get_anthropic_model() -> str:
    """Return the Claude model ID to call for advisory reviews.

    Anthropic's current models page lists `claude-sonnet-4-6` as the latest Sonnet API alias,
    so we default to that stable alias and allow `ANTHROPIC_MODEL` to override it if the
    workflow needs to pin or roll forward without another code change.
    """
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)


def get_max_tokens() -> int:
    """Return the max_tokens budget for Claude review responses."""
    raw = os.environ.get("ANTHROPIC_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_TOKENS
    return max(256, value)


def extract_claude_review(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract review text and stop reason from Anthropic messages responses."""
    content = data.get("content", [])
    review = "\n".join(block.get("text", "") for block in content if block.get("type") == "text").strip()
    return review, {"stop_reason": data.get("stop_reason")}


def fetch_claude_review(api_key: str, prompt: str) -> str:
    """Call Anthropic and return the advisory review body.

    The workflow is expected to provide `ANTHROPIC_API_KEY`; HTTP errors are surfaced with a non-zero
    exit code so the advisory workflow can post a skip/failure notice instead of silently succeeding.
    """
    payload = {
        "model": get_anthropic_model(),
        "max_tokens": get_max_tokens(),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    review, extra = fetch_review(
        "https://api.anthropic.com/v1/messages", headers, payload, extract_claude_review, "Claude"
    )
    if extra.get("stop_reason") == "max_tokens":
        review = (
            f"{review}\n\n"
            "_Note: Claude hit the review token budget before finishing. "
            "Consider increasing `ANTHROPIC_MAX_TOKENS` if this keeps happening._"
        ).strip()
    return review


def main() -> int:
    """Run the advisory Claude review flow."""
    context = load_review_context("ANTHROPIC_API_KEY")
    if not context.diff.strip():
        return emit_empty_diff_notice("Claude")

    prompt = build_prompt(context.pr_title, context.diff, context.issue_body)
    review = fetch_claude_review(context.api_key, prompt)
    return finalize_review(review, "ERROR: Claude API returned an empty review")


if __name__ == "__main__":
    raise SystemExit(main())
