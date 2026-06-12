"""GPT AI code review script called by gpt-pr-review.yml."""

from __future__ import annotations

from typing import Any

from review_common import build_prompt, emit_empty_diff_notice, fetch_review, finalize_review, load_review_context


def extract_openai_review(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract review text from OpenAI chat-completions responses."""
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


def fetch_openai_review(api_key: str, prompt: str) -> str:
    """Call OpenAI and return the advisory review body.

    The workflow is expected to provide `OPENAI_API_KEY`; HTTP errors are surfaced with a non-zero
    exit code so the advisory workflow can post a skip/failure notice instead of silently succeeding.
    """
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    review, _extra = fetch_review(
        "https://api.openai.com/v1/chat/completions", headers, payload, extract_openai_review, "OpenAI"
    )
    return review


def main() -> int:
    """Run the advisory GPT review flow."""
    context = load_review_context("OPENAI_API_KEY")
    if not context.diff.strip():
        return emit_empty_diff_notice("GPT")

    prompt = build_prompt(context.pr_title, context.diff, context.issue_body)
    review = fetch_openai_review(context.api_key, prompt)
    return finalize_review(review, "ERROR: OpenAI API returned an empty review")


if __name__ == "__main__":
    raise SystemExit(main())
