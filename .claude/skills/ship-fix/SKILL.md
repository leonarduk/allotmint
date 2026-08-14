---
name: ship-fix
description: Take a scoped code fix from a dirty/main checkout to a proper branch, commit, and PR following this repo's branch policy (docs/CONTRIBUTING.md) — never commits to main, uses a clean worktree when the checkout is dirty, keeps unrelated findings out of the diff, and links the PR to its issue with "Closes #N". Use whenever about to commit or push a fix for allotmint, or when told to "ship this", "open a PR for X", or "move this to a branch".
---

# Ship a fix properly

This repo's #1 rule (`docs/CONTRIBUTING.md`): never commit directly to `main`.
This skill is the checklist for going from "I have a fix" (possibly sitting
uncommitted on a dirty `main` checkout) to a mergeable PR without violating that,
and without smuggling unrelated changes along for the ride.

## 1. Assess the starting state

```
git status --short
git log --oneline -5 main
```

- If `main` is clean and you haven't written the fix yet: create the branch
  *first* (see step 2), then write the fix. Don't edit-then-branch.
- If `main` already has uncommitted changes (yours or pre-existing) when you
  reach this point: **don't just branch in place** — a branch created from a
  dirty checkout carries whatever else was sitting there, silently. Stash first:

  ```
  git stash push -u -m "<description>" -- <specific files, not -A>
  git status --short   # confirm main is clean
  ```

## 2. Create a clean worktree + branch off the remote

```
git fetch origin main -q
git worktree add ../<repo>-fix-<issue-number> -b fix/issue-<N>-<short-slug> origin/main
```

Branch naming: `fix/issue-NNNN-short-description`, `feat/issue-NNNN-...`,
or `docs/...` per `docs/CONTRIBUTING.md`.

If you stashed in step 1, apply *only the relevant files* into the new worktree:

```
git -C ../<repo>-fix-<issue-number> stash apply stash@{0}
git -C ../<repo>-fix-<issue-number> checkout -- <files that belong to a different, unrelated finding>
```

Don't ship two unrelated fixes in one PR just because they were sitting in the
same stash — split them into separate branches/PRs (see #6494 vs #6493 in this
repo's history for why: they looked related but needed independent design
decisions, and bundling them would have blocked the easy one on the hard one).

## 3. Before committing

- Re-read the **full current content** of every file you're changing from disk —
  not a diff, not memory of an earlier read (`CLAUDE.md` rule #1).
- Verify the fix live: reload the app in the Browser pane, exercise the exact
  repro from the issue, confirm it's actually fixed (not just "looks right").
- Run the narrowest relevant test/lint command, not the full suite, unless the
  change is broad.
- If the diff drifted to include formatting-only changes to unrelated lines
  (e.g. from an editor auto-format), split those into a separate commit —
  don't bury the real diff in cosmetic noise (`docs/CONTRIBUTING.md`).

## 4. Commit, push, PR

- Stage explicit files — never `git add -A` / `git commit -am` (risk of sweeping
  in lockfile drift or unrelated changes).
- Commit message: what changed and why, not a restatement of the diff.
- `git push -u origin <branch>`.
- `gh pr create` with a body containing `Closes #<issue-number>` so the issue
  auto-closes on merge, plus a `## Test plan` section listing what you actually
  verified (live browser check, not just "should work").

## 5. If you have multiple ready fixes

Prefer one branch/PR per logical change over one big branch. If several fixes
share a root cause (e.g. they'd all be touched by the same refactor), that's a
signal to slow down and call it out to the user rather than bundling — this
repo's own regression history (the Portfolio UX merge, #6470) is what happens
when several logically-separate changes land in one PR.
