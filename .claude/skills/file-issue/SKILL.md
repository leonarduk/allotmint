---
name: file-issue
description: File a well-formed GitHub issue for this repo — searches for an existing duplicate first, then uses the exact section headers from .github/ISSUE_TEMPLATE (bug_report.md or feature_request.md), the repo's Value rubric, and cites real file:line evidence rather than guesses. Use whenever logging a bug, regression, or product/enhancement finding for allotmint — including when asked to "log this", "file an issue", "create an issue for X", or as the filing step inside a larger QA pass.
---

# File a well-formed issue

This repo enforces a specific issue shape (see `CLAUDE.md`: "Always use the
template format... and include every required section"). Free-form issues get
rejected or ignored in triage. This skill is the mechanical part of that —
composition and evidence-gathering are still on you.

## 1. Search first

Before creating anything, check whether this is already tracked:

```
gh issue list --repo leonarduk/allotmint --search "<key terms>" --state all
```

or `mcp__github__search_issues`. If you find the same root cause reached via a
different repro path, add a comment (`mcp__github__add_issue_comment`) to the
existing issue instead of opening a new one — quote the new repro, note what's
different, and link back if relevant (e.g. "also reproduces via bare `/portfolio`,
see #6492").

## 2. Pick the template

- `.github/ISSUE_TEMPLATE/bug_report.md` — something is broken or behaves
  incorrectly. Label `bug`.
- `.github/ISSUE_TEMPLATE/feature_request.md` — something should be built,
  changed, or is a product/architecture judgment call (consolidation candidates,
  incomplete features, disabled-route UX, etc.). Label `enhancement`.
- Add `performance` alongside `bug` when latency/redundant-requests are the
  finding.

Both templates share the same section skeleton — use these exact headers,
in order, every time:

```
## What
## Why
## How
## Files Affected
## Constraints
## LLM tier
## Value
## Success looks like
## Failure looks like
```

## 3. Fill each section with evidence, not vibes

- **What**: exact repro — URL/route, steps, and what you actually observed
  (quote console errors, network status codes, or screenshot findings inline).
  Don't paraphrase an error message you saw; paste it.
- **Why**: user/dev impact. "This looks wrong" is not a reason; "this blocks
  every owner-scoped page" is.
- **How**: cite `file:line` you actually opened and read. If multiple files are
  plausibly involved, list them and say which one needs confirmation — don't
  assert a fix location you haven't verified. For product/architecture findings,
  say explicitly "no mechanical fix proposed — needs a product decision" rather
  than implying a clean patch exists.
- **Files Affected**: repo-relative paths only, one per line.
- **Constraints**: anything the fix must not break (e.g. "must not regress the
  existing group-view", "don't remove the config flag without confirming nothing
  else depends on it").
- **LLM tier**: haiku (mechanical/additive) / sonnet (judgment required) / opus
  (complex, cross-cutting, or needs a product decision first).
- **Value**: use the repo's own rubric, don't invent one —
  - High: real bugs, security/auth gaps, financial-data correctness, substantive
    product features.
  - Medium: reliability/observability with real but non-urgent blast radius, or
    consolidated hardening/test-coverage backlogs.
  - Low: single-file mechanical fixes, renames, doc/formatting, or discussion-
    starter product observations with no functional risk.
- **Success/Failure looks like**: concrete, checkable — "X request fires once"
  not "the bug is fixed."

## 4. File it

`mcp__github__create_issue` with `owner: "leonarduk"`, `repo: "allotmint"`,
the title, `labels`, and the body assembled above. If the user gave a milestone
for a batch of issues, apply it afterward with `mcp__github__update_issue` —
batch these in parallel across all the issues in the set rather than one at a
time.

## 5. Cross-link

If this finding blocks or relates to other open issues (e.g. "can't test X until
issue #N is fixed"), say so explicitly in the body or a follow-up comment — this
kind of dependency note has real value for whoever triages next (see #6492's
comment thread for the pattern: noting it blocked verification of a second issue).
