This directory is reserved for QA-generated screenshots that demonstrate page layouts across supported platforms.

During each release cycle, the QA team should capture and commit up-to-date screenshots for every page/platform combination.

If no screenshots are available, leave this `.gitkeep` file in place to retain the directory structure.

## Demo walkthrough (offline fallback)

`demo/` holds a short, ordered walkthrough for the interview/demo flow —
Cognito hosted-UI login → portfolio dashboard → one drill-down — captured as
annotated screenshots plus a self-contained `index.html`. It exists so the
flow can be presented from disk with **no live network/VPN access** to the
app or localhost.

Regenerate it with the existing capture script (see
[`docs/CONTRIBUTOR_RUNBOOK.md`](../../CONTRIBUTOR_RUNBOOK.md) § "Regenerating
the docs screenshots"):

```bash
DATA_ROOT=data bash scripts/bash/run-local-api.sh   # backend
npm --prefix frontend run dev                        # frontend, :2568
node frontend/scripts/capture-qa-screenshots.mjs --demo
```

Then open `demo/index.html` directly in a browser. The login step is
best-effort: if the Cognito hosted UI isn't reachable (no network, or auth
disabled locally) it is skipped and the walkthrough starts at the dashboard.
