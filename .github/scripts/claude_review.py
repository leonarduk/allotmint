"""Claude AI code review script called by claude-pr-review.yml."""

import json
import os
import sys
import urllib.error
import urllib.request

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

pr_title = os.environ.get("PR_TITLE", "")
diff = os.environ.get("DIFF", "")
issue_body = os.environ.get(
    "ISSUE_BODY", "No linked issue found. Review code on its own merits."
)

prompt = f"""You are a senior engineer reviewing a pull request for **allotmint**,
a family investment management app.

The stack is Python/FastAPI backend + React/Vite TypeScript frontend + AWS Lambda/CDK infrastructure.
Key constraints: preserve portfolio/compliance correctness, keep backend/frontend contracts aligned,
and avoid regressions in CI/deployment workflows.

## Linked issue / acceptance criteria
{issue_body}

## PR title
{pr_title}

## Diff (Python, TypeScript, JavaScript, JSON, Markdown, config files — truncated at 30k chars)
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
Any incorrect behaviour, edge cases that aren't handled, or off-by-one errors?
For documentation PRs: are there factual errors, contradictions, or dangerously
misleading statements?

### 3. API, data, and workflow safety
- Do backend/frontend payload shapes still line up?
- Could this break local smoke tests, deployment workflows, or repo scripts?
- Are secrets, permissions, or CI assumptions handled safely?

### 4. Test coverage
Are the acceptance criteria actually exercised by tests or validation steps? Any obvious missing cases?
Not applicable for documentation-only PRs, but note if validation is missing.

### 5. Minor issues (optional)
Style, naming, docs — only flag if they would cause future confusion.

End with a one-line summary verdict: **APPROVE**, **REQUEST CHANGES**,
or **COMMENT** (no blocking concerns but worth noting).
"""

payload = {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 1500,
    "messages": [{"role": "user", "content": prompt}],
}

req = urllib.request.Request(
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"ERROR: Claude API returned {e.code}: {body}", file=sys.stderr)
    sys.exit(1)

review = data["content"][0]["text"].strip()
if not review:
    print("ERROR: Claude API returned an empty review", file=sys.stderr)
    sys.exit(1)

print(review)
