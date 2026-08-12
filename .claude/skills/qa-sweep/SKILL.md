---
name: qa-sweep
description: Explore-and-log QA pass over the AllotMint frontend. Drives the app in the Browser pane across every nav route (and mobile/tablet/theme variants), classifies what it finds (broken / incomplete / duplicate-or-overlapping / consolidation candidate), and files GitHub issues using the repo's bug_report/feature_request templates. Does NOT fix code. Use when asked to "QA the app", "log issues", "audit the UI", "find regressions", or "redo the QA sweep".
---

# QA sweep (log-only, no fixes)

Goal: find real problems by actually driving the running app, and leave a clean paper
trail of GitHub issues — not a pile of unreviewed local edits. This skill is
**log-only by default**: identify and file, don't patch, unless the user explicitly
asks for a fix in the same turn.

Treat this as an iterative loop across a session, not a single pass: the user will
likely say "keep going" repeatedly. Each iteration should open genuinely new ground
(new page, new viewport, new interaction) rather than re-describing what's already
been reported.

## 0. Ground rules

- **Never commit to `main` or edit files as a side effect of QA.** If you spot an
  obvious one-line fix, resist the urge — file it instead. If the user explicitly
  asks you to fix something mid-sweep, follow the branch/worktree/PR policy in
  `docs/CONTRIBUTING.md` (never commit to `main`, create a branch first, open a PR)
  — see the "If asked to fix" section below.
- **Read `CLAUDE.md` and `docs/CONTRIBUTING.md`** (specifically the branch/PR policy
  and issue-template requirements) before filing anything if you haven't already
  this session.
- **Search before filing.** For every finding, check whether an open issue already
  covers it (`mcp__github__search_issues` or `gh issue list --search`) before
  creating a new one. If it's the same root cause via a different repro path, add a
  comment to the existing issue instead of opening a duplicate.
- **Don't guess at severity.** Use the repo's own `## Value` rubric (High/Medium/Low,
  defined in the issue templates) rather than inventing your own scale.
- **Distinguish confirmed bugs from hypotheses.** If you can't pin the exact root
  cause, say so in the issue body ("needs investigation") rather than asserting a
  fix location you haven't verified by reading the code.

## 1. Set up

1. Confirm a dev server is already running (check `.claude/launch.json` for the
   `frontend` config) — prefer attaching to whatever's already up over starting a
   fresh one (`mcp__Claude_Browser__preview_start` with `{url: "http://localhost:5173"}`
   if something's already bound to that port).
2. Skim `frontend/src/routes/registry.ts` and the nav menu components
   (`frontend/src/components/Menu.tsx` / `AppHeader.tsx`) to build a checklist of
   every route reachable from the nav, plus any deep-link-only routes.
3. Check `config.yaml`'s `ui.tabs` block and `enable_*` flags — routes disabled here
   will redirect/gate rather than render; know this going in so you don't file a
   "broken route" issue for something that's deliberately off (but *do* flag if the
   disabled-route UX itself is bad — see #6521 for precedent).

## 2. Sweep loop

For each route/surface not yet covered this session:

1. Navigate, wait for load, `get_page_text` — does real content render, or is it
   stuck loading / blank / an error banner?
2. `read_console_messages({onlyErrors: true})` and `read_network_requests` — look
   for non-2xx responses, React warnings (duplicate keys, act() warnings), and
   requests that seem redundant (same URL fired 3+ times on one load — this found
   a real bug last time, see #6573).
3. If the page has forms or interactive controls, exercise them: submit empty
   (validation should reject, not silently no-op or 500), submit valid input,
   check the happy path actually completes. Use `javascript_tool` to click by text
   content when refs are unreliable (virtualized tables often don't expose full
   `read_page` trees).
4. Note anything that reads as: incomplete/stub (nav item leads to near-empty
   content), duplicate/overlapping (two pages answer the same question), or a
   combine/drop/expand candidate — these are as valuable as hard bugs, just file
   them under `enhancement` with "no mechanical fix proposed, needs a product
   decision" framing rather than pretending there's a clean fix.

Once the nav sweep is done, repeat the same loop for:
- **Mobile** (`resize_window({preset:"mobile"})`, 375×812) — reload, screenshot if
  the Browser pane is displaying, and specifically watch for: overlapping chart
  labels, horizontal-scroll dead zones, clipped text at viewport edges.
- **Tablet** (`resize_window({preset:"tablet"})`).
- **Light theme** (`resize_window({colorScheme:"light"})` + reload) — confirm the
  "system" theme config actually follows OS preference; this repo has shipped that
  bug before (#6530).
- **Any owner/config-gated states**: with `disable_auth: true` locally, you can
  usually reach every state directly, but note if a whole feature category (e.g.
  every owner-scoped page) is unreachable due to a bug upstream — that's worth its
  own high-priority issue, not just noting each blocked page individually.

If a screenshot tool call fails with "Browser pane is not displayed," fall back to
`get_page_text` + `read_page`/`read_console_messages`/`read_network_requests` for the
rest of the session rather than blocking on it.

## 3. Filing issues

Use `mcp__github__create_issue` with the exact section headers from
`.github/ISSUE_TEMPLATE/bug_report.md` (bugs) or `feature_request.md`
(incomplete/duplicate/combine/drop/expand findings): `## What`, `## Why`, `## How`,
`## Files Affected`, `## Constraints`, `## LLM tier`, `## Value`,
`## Success looks like`, `## Failure looks like`. Label `bug` or `enhancement`
accordingly; add `performance` too when relevant.

- `## What`: exact repro (URL/route, steps, what you observed) — screenshots or
  network/console evidence quoted inline where you have them.
- `## Why`: user/dev impact, not just "this looks wrong."
- `## How`: cite specific `file:line` you actually read, not a guess. If several
  files are plausibly involved, list them and say which needs confirmation.
- For consolidation/product findings: explicitly note in `## How` that this needs a
  product decision, not a mechanical patch — don't imply there's an obvious fix that
  isn't there.
- If the user gave a milestone, apply it to every issue via `mcp__github__update_issue`
  (`milestone: <number>`) — batch these calls in parallel.
- If a finding is the *same bug* reached via a second repro path, add a comment to
  the existing issue (`mcp__github__add_issue_comment`) instead of a new issue —
  this repo's issue count is already large; don't inflate it.

## 4. If asked to fix (not the default — only when explicitly requested)

1. `git status` — if dirty, `git stash` the relevant files.
2. `git worktree add ../<repo>-fix-<issue-number> -b fix/issue-<N>-<slug> origin/main`.
3. Apply the fix there, re-read the full file first (per `CLAUDE.md`), keep the diff
   scoped to one logical change — don't bundle an unrelated finding into the same PR
   just because you found it in the same session.
4. Verify live in the browser before committing.
5. Commit (stage explicit files, never `-a`), push, `gh pr create` with `Closes #N`
   in the body.
6. If you have several fixes ready but they're independent, prefer separate
   branches/PRs over one big one — this repo's own history shows large multi-file
   UX PRs are exactly what caused the regressions this skill exists to catch.

## 5. Resuming a sweep after fixes land

When the user says fixes have merged and asks you to continue:

1. `git log --oneline -20 main` to see what actually landed — don't assume from
   memory which issues are closed.
2. Check the state of every issue you filed this session in one batch (a loop of
   `gh issue view $n --json state` is fine) rather than re-testing everything blind.
3. Re-verify closed items live (quick smoke check, not a full re-audit) and spend
   the rest of the budget on genuinely new ground — previously-blocked flows
   (anything gated behind a now-fixed crash), interaction paths not yet tried,
   viewport/theme combinations not yet tried.

## Reference: prior run

The first full run of this skill against this repo (2026-08-11) found 20 issues in
one session, 13 of which were fixed within the same day by parallel work — see
issues #6492–#6534, #6573 and PR #6496 for calibration on the level of detail and
evidence expected per finding.
