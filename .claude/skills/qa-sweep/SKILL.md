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

## Tool mapping for non-Claude agents (Kun / Codex)

The procedure above is tool-agnostic; only the tool names are Claude-specific.
Non-Claude agents should follow the same methodology with this mapping, and flag
gaps honestly — never fabricate console/network evidence you could not collect.

When the Playwright MCP server is connected (Kun: configured in `~/.kun/mcp.json`
as server id `playwright`, `npx -y @playwright/mcp@latest`), prefer its
`mcp_playwright_browser_*` tools for console/network/viewport evidence; otherwise
the rows marked "requires Playwright MCP" are unavailable.

| Claude tool (as written above) | Equivalent here | Notes |
|---|---|---|
| `mcp__Claude_Browser__preview_start` / Browser pane | `browser_use` `open` / `snapshot` / `screenshot` / `click` / `type` / `press` / `scroll` / `wait` / `tabs` | Same fallback rule: if screenshot fails with "pane not displayed", fall back to `snapshot` + page text for the rest of the session. |
| `get_page_text` / `read_page` | `browser_use` `snapshot` (accessible-name tree), or `mcp_playwright_browser_snapshot` | Re-snapshot after every navigation; build locators only from the latest snapshot. |
| `read_console_messages({onlyErrors})` | `mcp_playwright_browser_console_messages` (pass `level: "error"` for onlyErrors) | Requires Playwright MCP; otherwise **not available** — say so in the issue. |
| `read_network_requests` | `mcp_playwright_browser_network_requests`, then `mcp_playwright_browser_network_request` for per-request details | Requires Playwright MCP; see #6573 for the duplicate-request pattern to look for. |
| `javascript_tool` (click by text when refs are unreliable) | `browser_use` `click` on the role/name ref from the latest snapshot; `mcp_playwright_browser_run_code_unsafe` only as a last resort | `browser_run_code_unsafe` executes arbitrary JS in the MCP process (RCE-equivalent) — never use it without explicit user approval; prefer `browser_use` clicks. |
| `resize_window({preset:"mobile"/"tablet"})` | `mcp_playwright_browser_resize` (mobile = 375×812, tablet = 768×1024) | Requires Playwright MCP. |
| `resize_window({colorScheme:"light"})` | No exact equivalent in the connected MCP catalog — check available tools for theme emulation; otherwise note the gap in the issue. | |
| `mcp__github__search_issues` | `gh issue list --search`, or `mcp_github_search_issues` (gh CLI is authed as leonarduk) | |
| `mcp__github__create_issue` | `cicaid create-issue` (preferred when installed — see below), `mcp_github_create_issue`, or `gh issue create` | |
| `mcp__github__add_issue_comment` | `gh issue comment`, or `mcp_github_add_issue_comment` | |
| `mcp__github__update_issue` | `gh issue edit`, or `mcp_github_update_issue` | |

### Capability gaps to state in issues, not hide

- Console and network evidence comes from the Playwright MCP server
  (`mcp_playwright_browser_*`). When it is connected, quote real console/network
  findings (e.g. the #6573 redundant-request class). When it is **not**
  connected, write `"no console/network evidence — verified visually/DOM only"`
  in `## How` rather than implying it was checked.
- Mobile/tablet passes are available via `mcp_playwright_browser_resize` when
  the MCP is connected; light-theme emulation has no exact equivalent — if a
  theme check can't be done, say so in the issue instead of pretending it was.

### Filing issues via cicaid (preferred on leonarduk's machines)

`cicaid` (github.com/leonarduk/cicaid, pip-installed CLI) is the repo owner's
issue/PR automation tool and the preferred filing path when available.
`cicaid create-issue` uses the repo's own template sections, auths via
`GITHUB_TOKEN` or `gh auth token`, and creates via the GitHub API with a `gh`
CLI fallback. Sibling commands (`sync-issues`, `triage-issues`,
`clear-ai-slop-issues`) cover the other issue-management chores.

It is interactive but fully pipeable — every prompt reads stdin. Drive it
non-interactively with an answer stream:

1. `b` (bug) or `f` (feature) — issue type
2. For each template section in order (What, Why, How, Files Affected,
   Constraints, LLM tier, Value, Success looks like, Failure looks like):
   the section text, then a line containing just `.` to finish that input
3. Title (single line), Labels (comma-separated), then `n` (skip the LLM
   review — content should already be drafted/evidenced), `y` (create),
   `n` (don't start work on it)

Set `CICAID_SKIP_UPDATE_CHECK=1` for non-interactive runs.

Repo-label reality check: the repo has no "Value" labels — use the real label
set (`bug`, `enhancement`, `performance`, `frontend`, `backend`,
`accessibility`, `codex`, `haiku`/`sonnet`/`opus`, ...). Confirm with
`gh label list` before filing.

Windows environment notes (observed 2026-08-13): the GitHub MCP server token
was invalid ("Bad credentials") — use `gh` or cicaid instead; and `gh issue
view --json body` output can be mojibake'd at the terminal on this machine —
write bodies via `--body-file` and decode reads by piping JSON to a file and
loading it with Python rather than trusting terminal output.

### Trigger note

Repo-local skills are not auto-activated by non-Claude agents (their skill
catalogs are global). Read this file explicitly before any QA/issue work; an
`AGENTS.md` pointer to this skill is the reliable way to trigger it.

## Tool mapping for non-Claude agents (Kun / Codex)

The procedure above is tool-agnostic; only the tool names are Claude-specific.
Non-Claude agents should follow the same methodology with this mapping, and flag
gaps honestly — never fabricate console/network evidence you could not collect.

When the Playwright MCP server is connected (Kun: configured in `~/.kun/mcp.json`
as server id `playwright`, `npx -y @playwright/mcp@latest`), prefer its
`mcp_playwright_browser_*` tools for console/network/viewport evidence; otherwise
the rows marked "requires Playwright MCP" are unavailable.

| Claude tool (as written above) | Equivalent here | Notes |
|---|---|---|
| `mcp__Claude_Browser__preview_start` / Browser pane | `browser_use` `open` / `snapshot` / `screenshot` / `click` / `type` / `press` / `scroll` / `wait` / `tabs` | Same fallback rule: if screenshot fails with "pane not displayed", fall back to `snapshot` + page text for the rest of the session. |
| `get_page_text` / `read_page` | `browser_use` `snapshot` (accessible-name tree) | Re-snapshot after every navigation; build locators only from the latest snapshot. |
| `read_console_messages({onlyErrors})` | `mcp_playwright_browser_console_messages` (pass `level: "error"` for onlyErrors) | Requires Playwright MCP; otherwise **not available** — say so in the issue. |
| `read_network_requests` | `mcp_playwright_browser_network_requests`, then `mcp_playwright_browser_network_request` for per-request details | Requires Playwright MCP; see #6573 for the duplicate-request pattern to look for. |
| `javascript_tool` (click by text when refs are unreliable) | `browser_use` `click` on the role/name ref from the latest snapshot; `mcp_playwright_browser_run_code_unsafe` only as a last resort | `browser_run_code_unsafe` executes arbitrary JS in the MCP process (RCE-equivalent) — never use it without explicit user approval; prefer `browser_use` clicks. |
| `resize_window({preset:"mobile"/"tablet"})` | `mcp_playwright_browser_resize` (mobile = 375×812, tablet = 768×1024) | Requires Playwright MCP. |
| `resize_window({colorScheme:"light"})` | No exact equivalent in the connected MCP catalog — check available tools for theme emulation; otherwise note the gap in the issue. | |
| `mcp__github__search_issues` | `mcp_github_search_issues`, or `gh issue list --search` (gh CLI is authed as leonarduk) | |
| `mcp__github__create_issue` | `mcp_github_create_issue`, or `gh issue create` | |
| `mcp__github__add_issue_comment` | `mcp_github_add_issue_comment`, or `gh issue comment` | |
| `mcp__github__update_issue` | `mcp_github_update_issue`, or `gh issue edit` | |

### Capability gaps to state in issues, not hide

- Console and network evidence comes from the Playwright MCP server
  (`mcp_playwright_browser_*`). When it is connected, quote real console/network
  findings (e.g. the #6573 redundant-request class). When it is **not**
  connected, write `"no console/network evidence — verified visually/DOM only"`
  in `## How` rather than implying it was checked.
- Mobile/tablet passes are available via `mcp_playwright_browser_resize` when
  the MCP is connected; light-theme emulation has no exact equivalent — if a
  theme check can't be done, say so in the issue instead of pretending it was.

### Trigger note

Repo-local skills are not auto-activated by non-Claude agents (their skill
catalogs are global). Read this file explicitly before any QA/issue work; an
`AGENTS.md` pointer to this skill is the reliable way to trigger it.
