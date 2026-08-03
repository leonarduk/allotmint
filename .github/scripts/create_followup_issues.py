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
from typing import Callable

from llm_labels import extract_tier_label, extract_value_label

_PR_FOOTER_TEMPLATE = "_Follow-up suggested by AI review of PR #{pr_number}._"

# Conversational preamble the model sometimes prepends before the real body,
# e.g. "Here is a complete, actionable GitHub issue body based on your request."
_PREAMBLE_RE = re.compile(
    r"^(here('?s| is| are)|below (is|are)|sure|certainly|of course|okay|ok|"
    r"this is|i('ve| have) (written|drafted|created))\b",
    re.IGNORECASE,
)
_HORIZONTAL_RULES = {"---", "***", "___"}

# Provider used to generate rich issue bodies, selectable via FOLLOWUP_LLM_PROVIDER.
# Defaults to deepseek, the repo's primary required PR reviewer.
_DEFAULT_PROVIDER = "deepseek"


def _strip_wrapping_code_fence(body: str) -> str:
    """Unwrap a body the model enclosed in a single ``` or ```markdown fence."""
    lines = body.splitlines()
    if len(lines) >= 2 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return body


def _drop_leading_hrule(lines: list[str]) -> list[str]:
    """Drop leading blank lines and a single leftover horizontal-rule separator."""
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].strip() in _HORIZONTAL_RULES:
        return lines[idx + 1 :]
    return lines


def _sanitize_body(text: str) -> str:
    """Strip conversational preamble and wrapping fences the LLM may add.

    Models occasionally prefix the body with a line like "Here is a complete,
    actionable GitHub issue body ..." followed by a `---` separator, or wrap the
    whole body in a ```markdown code fence. That wrapper text leaked verbatim
    into many historical issues; strip it so only the Markdown body remains.
    Internal `---` section dividers are preserved — only a leading one is removed.
    """
    body = _strip_wrapping_code_fence(text.strip())
    lines = body.splitlines()

    first = next((line for line in lines if line.strip()), "")
    if _PREAMBLE_RE.match(first.strip()):
        # Drop everything up to and including the preamble line, then any blank
        # lines and a `---` separator that follows it.
        lines = _drop_leading_hrule(lines[lines.index(first) + 1 :])

    return "\n".join(_drop_leading_hrule(lines)).strip()


def _build_prompt(title: str, pr_number: str, review_text: str) -> str:
    return f"""You are writing a GitHub issue for the allotmint repository.

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
6. **Value** — how much impact/priority this has: Low Value, Medium Value,
   or High Value
   - High Value: real bugs, security/auth gaps, financial-data correctness
     issues, or substantive product features
   - Medium Value: reliability/observability improvements with real (if
     non-urgent) blast radius, and consolidated multi-item
     hardening/test-coverage backlogs
   - Low Value: single-file "add a test for X" / rename / doc-comment /
     formatting-only suggestions with no functional risk
7. **Success looks like** — specific, verifiable criteria
8. **Failure looks like** — what would indicate the implementation went wrong

Be concise but complete. Do not pad with generic advice.

Output ONLY the raw Markdown issue body. Do not wrap it in a code fence and do
not add any preamble (e.g. "Here is the issue body") — start directly with the
first heading. When you name a file, function, or line number, use only paths
you can confirm from the review text above; if you are unsure, describe the
location instead of guessing a concrete path. Do not add a footer crediting the
source PR -- that is appended separately."""


def _call_anthropic(api_key: str, prompt: str) -> str:
    model = os.environ.get("ANTHROPIC_FOLLOWUP_MODEL", "claude-haiku-4-5-20251001")
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _openai_compatible_caller(
    url: str, model_env: str, default_model: str
) -> Callable[[str, str], str]:
    """Return a caller for OpenAI-compatible chat-completions APIs (OpenAI, DeepSeek)."""

    def _call(api_key: str, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": os.environ.get(model_env, default_model),
                "max_tokens": 1024,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()

    return _call


# Maps FOLLOWUP_LLM_PROVIDER values to (API key env var, caller).
_PROVIDERS: dict[str, tuple[str, Callable[[str, str], str]]] = {
    "claude": ("ANTHROPIC_API_KEY", _call_anthropic),
    "gpt": (
        "OPENAI_API_KEY",
        _openai_compatible_caller(
            "https://api.openai.com/v1/chat/completions", "OPENAI_FOLLOWUP_MODEL", "gpt-4o-mini"
        ),
    ),
    "deepseek": (
        "DEEPSEEK_API_KEY",
        _openai_compatible_caller(
            "https://api.deepseek.com/v1/chat/completions",
            "DEEPSEEK_FOLLOWUP_MODEL",
            "deepseek-v4-flash",
        ),
    ),
}


def _generate_body_via_llm(title: str, pr_number: str, review_text: str) -> str | None:
    """Call the configured LLM provider to generate a rich issue body.

    The provider is chosen via FOLLOWUP_LLM_PROVIDER (claude, gpt, or deepseek;
    defaults to deepseek). Returns None if the provider is unknown, its API key is
    unset, or the API call fails -- callers fall back to a minimal body.
    """
    # GitHub Actions sets unset `vars.*` to an empty string rather than omitting the
    # env var entirely, so `os.environ.get(..., default)` would not apply the default.
    provider = os.environ.get("FOLLOWUP_LLM_PROVIDER", "").strip().lower() or _DEFAULT_PROVIDER
    provider_config = _PROVIDERS.get(provider)
    if provider_config is None:
        print(
            f"WARNING: unknown FOLLOWUP_LLM_PROVIDER '{provider}', using fallback body",
            file=sys.stderr,
        )
        return None

    api_key_env, call = provider_config
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        return None

    prompt = _build_prompt(title, pr_number, review_text)
    try:
        return _sanitize_body(call(api_key, prompt))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        KeyError,
        IndexError,
        json.JSONDecodeError,
    ) as exc:
        print(f"WARNING: failed to generate issue body via {provider}: {exc}", file=sys.stderr)
        return None


def _build_body(title: str, pr_number: str, review_text: str | None) -> str:
    """Build the issue body, always ending with a footer linking back to the source PR.

    The prompt used to ask the model to end with a PR-linking footer itself, but that
    was unreliable: long responses got truncated (max_tokens) before reaching it, and
    models sometimes dropped it outright -- the #5845/#5846/#5847 batch of auto-filed
    follow-ups all shipped with no visible link back to PR #5830, the review that
    generated them. The footer is appended here unconditionally instead, so every
    follow-up issue is traceable back to its source PR regardless of what the model
    actually returned.
    """
    footer = _PR_FOOTER_TEMPLATE.format(pr_number=pr_number)
    body = _generate_body_via_llm(title, pr_number, review_text) if review_text else None
    if not body:
        return footer
    return f"{body}\n\n{footer}"


def issue_exists(title: str) -> bool:
    """Return True if an ai-suggested issue with this exact title already exists."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            "ai-suggested",
            "--search",
            title,
            "--json",
            "title",
            "--limit",
            "20",
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


def create_issues(titles: list[str], pr_number: str, review_text: str | None = None) -> list[str]:
    """Create each follow-up issue, returning titles that failed to create.

    A failure on one title (e.g. an unrecognized label) must not abort the
    remaining titles in the batch — a single bad `gh issue create` call
    previously raised uncaught and silently dropped every follow-up after it.
    """
    failed: list[str] = []
    for title in titles:
        if not title.strip():
            continue
        if issue_exists(title):
            print(f"Skipping (already exists): {title}")
            continue
        print(f"Creating issue: {title}")
        body = _build_body(title, pr_number, review_text)
        labels = ["ai-suggested"]
        llm_label = extract_tier_label(body)
        if llm_label:
            labels.append(llm_label)
        value_label = extract_value_label(body)
        if value_label:
            labels.append(value_label)
        label_args = [arg for label in labels for arg in ("--label", label)]
        try:
            subprocess.run(
                ["gh", "issue", "create", "--title", title, "--body", body, *label_args],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: failed to create issue '{title}': {exc}", file=sys.stderr)
            failed.append(title)
    return failed


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

    failed = create_issues(titles, pr_number, review_text)
    if failed:
        print(
            f"ERROR: {len(failed)} of {len(titles)} follow-up issue(s) failed to create",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
