"""DeepSeek AI code review script called by deepseek-pr-review.yml.

DeepSeek provides an OpenAI-compatible chat completions API at
https://api.deepseek.com/v1/chat/completions. The integration reuses the
shared `review_common` helpers so the prompt, verdict format, and error
handling stay identical across all three reviewers.
"""

from __future__ import annotations

import os
from typing import Any

from review_common import build_prompt, emit_empty_diff_notice, fetch_review, finalize_review, load_review_context

DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 4096


def get_deepseek_model() -> str:
    """Return the DeepSeek model ID to call for advisory reviews.

    Defaults to `deepseek-chat` (the latest DeepSeek-V3 alias). Set
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

    DeepSeek's API is OpenAI-compatible: the response shape is
    `{"choices": [{"message": {"content": "..."}}]}`.
    """
    choices = data.get("choices", [])
    if not choices:
        return "", {}

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        review = "\n".join(part.get("text", "") for part in content if part.get("type") == "text").strip()
    elif isinstance(content, str):
        review = content.strip()
    else:
        review = ""
    return review, {}


def fetch_deepseek_review(api_key: str, prompt: str) -> str:
    """Call DeepSeek and return the advisory review body.

    The workflow is expected to provide `DEEPSEEK_API_KEY`; HTTP errors are
    surfaced with a non-zero exit code so the advisory workflow can post a
    skip/failure notice instead of silently succeeding.
    """
    payload = {
        "model": get_deepseek_model(),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": get_max_tokens(),
        "temperature": 0.2,
    }
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

    prompt = build_prompt(context.pr_title, context.diff, context.issue_body, context.discussion, context.verified_facts)
    review = fetch_deepseek_review(context.api_key, prompt)
    return finalize_review(review, "ERROR: DeepSeek API returned an empty review")


if __name__ == "__main__":
    raise SystemExit(main())
