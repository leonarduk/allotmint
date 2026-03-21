"""Claude AI code review script called by claude-pr-review.yml."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

from review_common import build_prompt, emit_empty_diff_notice, finalize_review, load_review_context


ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"  # Update here when Anthropic promotes the next stable Sonnet model.


def extract_claude_review(data: dict[str, Any]) -> str:
    """Extract review text from Anthropic messages responses."""
    content = data.get("content", [])
    return "\n".join(block.get("text", "") for block in content if block.get("type") == "text").strip()


def fetch_claude_review(api_key: str, prompt: str) -> str:
    """Call Anthropic and return the advisory review body.

    The workflow is expected to provide `ANTHROPIC_API_KEY`; HTTP errors are surfaced with a non-zero
    exit code so the advisory workflow can post a skip/failure notice instead of silently succeeding.
    """
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Keep the provider response in stderr so maintainers can distinguish auth, quota, and API failures.
        body = exc.read().decode()
        print(f"ERROR: Claude API returned {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc

    return extract_claude_review(data)


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
