"""Create follow-up GitHub issues idempotently from a JSON list of titles."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
_FALLBACK_BODY_TEMPLATE = "Follow-up suggested by Claude AI review of PR #{pr_number}."

_LLM_LABEL_MAP = {
    "local-7b": "local-7b",
    "local-14b": "local-14b",
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
}
_LLM_TIER_PATTERN = re.compile(
    r'\*\*LLM\s+tier\*\*[^\n]*\n[^\n]*\*\*(local-14b|local-7b|haiku|sonnet|opus)\b',
    re.IGNORECASE,
)


def _generate_body_via_claude(title: str, pr_number: str, review_text: str) -> str:
    """Call Claude Haiku to generate a rich issue body. Returns the generated body."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _FALLBACK_BODY_TEMPLATE.format(pr_number=pr_number)

    prompt = f"""You are writing a GitHub issue for the allotmint repository.

The issue title is: "{title}"

It was suggested as a non-blocking follow-up during an AI code review of PR #{pr_number}.
The full review text is:
---
{review_text}
---

Write a complete, actionable GitHub issue body in Markdown covering:
1. **What** — exactly what needs to change and where (file, function, section)
2. **Why** — the motivation (correctness risk, maintainability, agent confusion, etc.)
3. **How** — a concrete implementation approach
4. **Constraints** — what must not break, what is out of scope
5. **LLM tier** — which model is appropriate:
   - local-7b: simple, mechanical changes a small local model can execute
     reliably (formatting, renames, obvious one-line fixes, mechanical
     refactors with no ambiguity)
   - local-14b: moderate reasoning a mid-size local model can handle
     (straightforward code review fixes, small well-scoped refactors,
     adding test cases that follow an existing pattern)
   - Haiku: simple/mechanical tasks better suited to cloud execution
     (e.g. needing broader repo context or tool access local models lack)
   - Sonnet: moderate design judgment (multi-file changes, non-trivial
     heuristics, new test coverage requiring design decisions)
   - Opus: complex design/architecture (cross-cutting changes, significant
     ambiguity, architectural trade-offs)
   Only recommend local-7b or local-14b when the task is genuinely simple
   and self-contained enough for a smaller model to complete correctly
   without broad context; default to the cloud tiers (Haiku/Sonnet/Opus)
   when in doubt
6. **Success looks like** — specific, verifiable criteria
7. **Failure looks like** — what would indicate the implementation went wrong

Be concise but complete. Do not pad with generic advice.
End with: _Follow-up from AI review of PR #{pr_number}._"""

    payload = json.dumps({
        "model": _ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        _ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"].strip()
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError) as exc:
        print(f"WARNING: failed to generate issue body via Claude API: {exc}", file=sys.stderr)
        return _FALLBACK_BODY_TEMPLATE.format(pr_number=pr_number)


def _extract_llm_label(body: str) -> str | None:
    """Return the tier label name (e.g. 'sonnet') if the body names a tier, else None."""
    m = _LLM_TIER_PATTERN.search(body)
    if m:
        return _LLM_LABEL_MAP.get(m.group(1).lower())
    for tier, label in _LLM_LABEL_MAP.items():
        if re.search(rf'\b{tier}\b', body, re.IGNORECASE):
            return label
    return None


def _build_body(title: str, pr_number: str, review_text: str | None) -> str:
    if review_text:
        return _generate_body_via_claude(title, pr_number, review_text)
    return _FALLBACK_BODY_TEMPLATE.format(pr_number=pr_number)


def issue_exists(title: str) -> bool:
    """Return True if an ai-suggested issue with this exact title already exists."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", "ai-suggested",
            "--search", title,
            "--json", "title",
            "--limit", "20",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return any(i.get("title", "").strip() == title.strip() for i in issues)


def create_issues(
    titles: list[str], pr_number: str, review_text: str | None = None
) -> None:
    for title in titles:
        if not title.strip():
            continue
        if issue_exists(title):
            print(f"Skipping (already exists): {title}")
            continue
        print(f"Creating issue: {title}")
        body = _build_body(title, pr_number, review_text)
        labels = ["ai-suggested"]
        llm_label = _extract_llm_label(body)
        if llm_label:
            labels.append(llm_label)
        label_args = [arg for label in labels for arg in ("--label", label)]
        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body, *label_args],
            check=True,
        )


def main() -> int:
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(
            f"Usage: {sys.argv[0]} <followups_json_file> <pr_number> [<review_file>]",
            file=sys.stderr,
        )
        return 1
    followups_file = sys.argv[1]
    pr_number = sys.argv[2]
    review_file = sys.argv[3] if len(sys.argv) == 4 else None

    try:
        with open(followups_file) as f:
            titles = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR reading {followups_file}: {exc}", file=sys.stderr)
        return 1

    review_text: str | None = None
    if review_file:
        try:
            review_text = Path(review_file).read_text()
        except FileNotFoundError:
            print(
                f"WARNING: review file not found: {review_file} — using fallback body",
                file=sys.stderr,
            )

    create_issues(titles, pr_number, review_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
