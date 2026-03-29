# Issue #2588 — Codex Implementation Tasks

This checklist is the execution plan for implementing issue [#2588](https://github.com/leonarduk/allotmint/issues/2588).

## 1) Preflight and branch safety
- [ ] Run `git status --short` to confirm working tree state.
- [ ] Run `git branch --show-current` and ensure current branch is not `main`.
- [ ] If on `main`, create/switch to `docs/issue-2588-claude-cdk-guidance`.

## 2) Instruction scope verification
- [ ] Check for nested `AGENTS.md` files that may apply to touched paths.
- [ ] Confirm active instructions before editing.

## 3) CLAUDE.md updates — High-signal warnings
- [ ] Add explicit rule: read full current file content before writing any fix.
- [ ] Wording must forbid relying on diff snippets alone.

## 4) CLAUDE.md updates — Preferred workflow
- [ ] Add step `0` requiring full-file reads before editing existing files.
- [ ] Keep existing workflow steps intact unless stale correction is required.

## 5) CLAUDE.md updates — CDK / Infrastructure section
- [ ] Add new `### CDK / Infrastructure` under `## If you touch specific areas`.
- [ ] Include guidance that CDK high-level grants (`grant_read_write`, etc.) may be broader than expected and must be audited.
- [ ] Include IAM/security guidance: trace actual handler call chain and cite `file:function` evidence in comments/PR descriptions.
- [ ] Prefer partition-safe ARN construction (`bucket.bucket_arn`, `bucket.arn_for_objects("*")`) over hard-coded `arn:aws:s3:::` strings.
- [ ] Remind that CDK tests synthesize templates; verify synthesized output rather than assuming code-to-template correspondence.

## 6) Preserve existing guidance
- [ ] Ensure changes are additive only (or explicit stale-content corrections).
- [ ] Avoid removing unrelated existing guidance.

## 7) AI-guidance alignment review
- [ ] Review `AGENTS.md` and `.github/copilot-instructions.md` for any minimal mirror updates needed.
- [ ] If no changes are needed, record rationale in PR description.

## 8) Validate acceptance criteria
- [ ] Run:
  - [ ] `rg -n "CDK / Infrastructure|read the full current|Preferred workflow|High-signal warnings|file:function" CLAUDE.md`
  - [ ] `git diff -- CLAUDE.md AGENTS.md .github/copilot-instructions.md`
- [ ] Confirm all issue acceptance criteria are met.

## 9) Commit hygiene
- [ ] Use one focused, imperative commit message.
- [ ] Example: `Strengthen CLAUDE guidance for CDK/IAM audit discipline`.

## 10) PR creation
- [ ] Open PR targeting `main`.
- [ ] Include in PR body:
  - [ ] What changed
  - [ ] Why it changed
  - [ ] Validation commands and outcomes
  - [ ] Known follow-up or risk
