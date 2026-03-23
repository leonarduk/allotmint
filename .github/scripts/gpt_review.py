"""GPT AI code review script called by gpt-pr-review.yml."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

from review_common import build_prompt, emit_empty_diff_notice, finalize_review, load_review_context


def extract_openai_review(data: dict[str, Any]) -> str:
    """Extract review text from OpenAI chat-completions responses."""
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content if part.get("type") == "text"
        ).strip()
    if isinstance(content, str):
        return content.strip()
    return ""


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
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Keep the provider response in stderr so maintainers can distinguish auth, quota, and API failures.
        body = exc.read().decode()
        print(f"ERROR: OpenAI API returned {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc

    return extract_openai_review(data)


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
