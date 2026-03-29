# Issue #2588 — Codex Implementation Tasks

This checklist records the implementation and validation work completed for issue [#2588](https://github.com/leonarduk/allotmint/issues/2588). It is retained as an audit trail for the documentation changes made in `CLAUDE.md`.

## 1) Preflight and branch safety
- [x] Run `git status --short` to confirm working tree state.
- [x] Run `git branch --show-current` and ensure current branch is not `main`.
- [x] Confirmed branch safety requirements were met before editing.

## 2) Instruction scope verification
- [x] Check for nested `AGENTS.md` files that may apply to touched paths.
- [x] Confirm active instructions before editing.

## 3) CLAUDE.md updates — High-signal warnings
- [x] Add explicit rule: read full current file content before writing any fix.
- [x] Wording forbids relying on diff snippets alone.

## 4) CLAUDE.md updates — Preferred workflow
- [x] Add step `0` requiring full-file reads before editing existing files.
- [x] Keep existing workflow steps intact unless stale correction is required.

## 5) CLAUDE.md updates — CDK / Infrastructure section
- [x] Add new `### CDK / Infrastructure` under `## If you touch specific areas`.
- [x] Include guidance that CDK high-level grants (`grant_read_write`, etc.) may be broader than expected and must be audited for least privilege.
- [x] Include IAM/security guidance: trace actual handler call chain and cite `file:function` evidence in comments/PR descriptions.
- [x] Prefer partition-safe ARN construction (`bucket.bucket_arn`, `bucket.arn_for_objects("*")`) over hard-coded `arn:aws:s3:::` strings, and clarify bucket/object scope differences.
- [x] Remind that CDK tests synthesize templates; verify synthesized output rather than assuming code-to-template correspondence.

## 6) Preserve existing guidance
- [x] Ensure changes are additive only (or explicit stale-content corrections).
- [x] Avoid removing unrelated existing guidance.

## 7) AI-guidance alignment review
- [x] Review `AGENTS.md` and `.github/copilot-instructions.md` for any minimal mirror updates needed.
- [x] No mirror updates were needed because issue #2588 acceptance criteria are specifically scoped to `CLAUDE.md`; rationale recorded in PR context.

## 8) Validate acceptance criteria
- [x] Run:
  - [x] `rg -n "CDK / Infrastructure|read the full current|Preferred workflow|High-signal warnings|file:function" CLAUDE.md`
  - [x] `git diff -- CLAUDE.md AGENTS.md .github/copilot-instructions.md`
- [x] Confirm all issue acceptance criteria are met.

## 9) Commit hygiene
- [x] Use one focused, imperative commit message.
- [x] Example: `Strengthen CLAUDE guidance for CDK/IAM audit discipline`.

## 10) PR creation
- [x] Open PR targeting `main`.
- [x] Include in PR body:
  - [x] What changed
  - [x] Why it changed
  - [x] Validation commands and outcomes
  - [x] Known follow-up or risk
