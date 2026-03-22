"""GPT AI code review script called by gpt-pr-review.yml.

Reads PR_TITLE, DIFF, ISSUE_BODY from environment variables,
calls the OpenAI Chat Completions API, and prints the review to stdout.
The workflow captures stdout and posts it as a PR comment.
"""

import json
import os
import sys
import urllib.error
import urllib.request

api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key:
    print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
    sys.exit(1)

pr_title = os.environ.get("PR_TITLE", "")
diff = os.environ.get("DIFF", "")
issue_body = os.environ.get(
    "ISSUE_BODY", "No linked issue found. Review code on its own merits."
)

prompt = f"""You are a senior engineer reviewing a pull request for **allotmint**,
a family investing platform with a FastAPI backend, a React/Vite frontend,
and GitHub Actions-based CI/CD.

The stack is Python/FastAPI backend + React/Vite frontend + AWS Lambda/CDK.
Key constraints: preserve existing backend/frontend workflows, keep CI advisory
jobs non-blocking, and align comments with the linked issue acceptance criteria.

## Linked issue / acceptance criteria
{issue_body}

## PR title
{pr_title}

## Diff (Python, JavaScript, JSON, YAML, Markdown, config files — truncated at 30k chars)
{diff}

If the diff is empty, this is likely a docs-only or config-only PR whose file types
were not captured. In that case, review the PR based solely on the linked issue
acceptance criteria and PR title, and note that no diff was available.

Review this PR across these dimensions. Be direct and specific — cite line numbers
or function names where relevant. If something looks fine, say so briefly.
Spend your words on real concerns.

### 1. Acceptance criteria
Does the diff satisfy every AC in the linked issue? Call out any gaps explicitly.
If no diff is available, assess whether the PR title and issue description suggest
the work is complete and correctly scoped.

### 2. Bugs and logic errors
Any incorrect behaviour, edge cases that aren't handled, or broken workflow logic?
For documentation PRs: are there factual errors, contradictions, or dangerously
misleading statements?

### 3. CI/CD and repo fit
(Especially for workflow/config changes)
- Are paths, commands, and file filters aligned with the allotmint repo?
- Could this duplicate or conflict with an existing workflow?
- Are advisory jobs correctly non-blocking when intended?

### 4. Test / validation coverage
Are the acceptance criteria actually exercised by tests or workflow validation?
If runtime validation cannot be done from the diff alone, call out the gap.

### 5. Minor issues (optional)
Style, naming, docstrings — only flag if they would cause future confusion.

End with a one-line summary verdict: **APPROVE**, **REQUEST CHANGES**,
or **COMMENT** (no blocking concerns but worth noting)."""

payload = {
    "model": "gpt-4o-mini",
    "messages": [
        {
            "role": "user",
            "content": prompt,
        }
    ],
    "temperature": 0.2,
}

req = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"ERROR: OpenAI API returned {e.code}: {body}", file=sys.stderr)
    sys.exit(1)

choices = data.get("choices", [])
review = ""
if choices:
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        review = "\n".join(
            part.get("text", "") for part in content if part.get("type") == "text"
        ).strip()
    elif isinstance(content, str):
        review = content.strip()

if not review:
    print("ERROR: OpenAI API returned an empty review", file=sys.stderr)
    sys.exit(1)

print(review)
