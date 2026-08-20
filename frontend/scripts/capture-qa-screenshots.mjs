// Refreshes docs/assets/qa-screenshots/*.png against the repo's own bundled
// demo dataset (data/accounts/demo-owner, data/accounts/alice) instead of a
// real private data checkout, so these images are safe to commit to a public
// repo and don't depend on any contributor's personal data.
//
// Requires the local dev servers already running:
//   DATA_ROOT=data bash scripts/bash/run-local-api.sh   (backend)
//   npm run dev                                         (frontend, :5173)
//
// Usage: node frontend/scripts/capture-qa-screenshots.mjs
// Not wired into CI -- run manually before a release / whenever the UI
// changes enough that the docs screenshots look stale.
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../../docs/assets/qa-screenshots");

// Local dev instances (e.g. separate worktrees/clones) each run their own
// backend on a port chosen by scripts/bash/run-local-api.sh or
// scripts/run-backend.ps1, recorded in .local/ports/backend.port at the
// repo root. Mirrors the same lookup in frontend/vite.config.ts (see #5760)
// so this script talks to the right backend instead of assuming :8000 is
// free.
function readLocalBackendPort() {
  const portFile = path.resolve(__dirname, "../..", ".local", "ports", "backend.port");
  try {
    const port = fs.readFileSync(portFile, "utf-8").trim();
    return /^\d+$/.test(port) ? port : null;
  } catch {
    return null;
  }
}

const BACKEND = `http://localhost:${readLocalBackendPort() ?? "8000"}`;
const FRONTEND = "http://localhost:5173";
const OWNER = "demo-owner";

// Text that indicates the page didn't actually render its real content --
// an auth wall, a disabled-feature notice, or a config error -- so a capture
// against one of these should be treated as a failure even though the page
// loaded without throwing.
const FAILURE_MARKERS = [
  "No local login override is configured",
  "This feature isn't enabled for this application",
];

// routeSegment/mode names match frontend/src/routes/registry.ts. `reports`
// is disabled by default in config.yaml -- toggled on for the duration of
// this script (see main()) and restored to its original value afterward.
// `transactions` stays skipped since it needs owner-scoped write context
// this script doesn't set up.
const PAGES = [
  { name: "portfolio-view.png", url: `/portfolio/${OWNER}`, waitFor: "VWRL.L" },
  { name: "mobile-portfolio-view.png", url: `/portfolio/${OWNER}`, waitFor: "VWRL.L", viewport: { width: 390, height: 844 } },
  { name: "dashboard.png", url: `/?group=all`, waitFor: "At a glance" },
  { name: "screener.png", url: "/screener", waitFor: "Run" },
  // NOTE: nested under `ui.tabs`, not top-level `tabs` -- PUT /config has a
  // bug (backend/routes/config.py _normalise_config_structure) where a
  // top-level `tabs` payload gets clobbered back to its stored value by a
  // reversed deep_merge call. Sending it pre-nested under `ui` skips that
  // buggy code path. See issue filed for the backend fix.
  { name: "reports.png", url: "/reports", waitFor: "Report templates", requiresConfig: { ui: { tabs: { reports: true } } } },
  { name: "market.png", url: "/market", waitFor: null },
  { name: "movers.png", url: "/movers", waitFor: null },
  { name: "watchlist.png", url: "/watchlist", waitFor: null },
  { name: "allocation.png", url: "/allocation", waitFor: null },
  { name: "rebalance.png", url: "/rebalance", waitFor: null },
  { name: "performance.png", url: `/performance/${OWNER}`, waitFor: null },
  { name: "trading.png", url: "/trading", waitFor: null },
  { name: "timeseries.png", url: "/timeseries", waitFor: null },
  { name: "instrumentadmin.png", url: "/instrumentadmin", waitFor: null },
  { name: "dataadmin.png", url: "/dataadmin", waitFor: null },
  { name: "data-quality.png", url: "/data-quality", waitFor: null },
  { name: "data-explorer.png", url: "/data-explorer", waitFor: null },
  { name: "alert-settings.png", url: "/alert-settings", waitFor: null },
  { name: "settings.png", url: "/settings", waitFor: null },
  { name: "pension.png", url: "/pension/forecast", waitFor: null },
  { name: "support.png", url: "/support", waitFor: null },
  { name: "scenario.png", url: "/scenario", waitFor: null },
  { name: "virtual.png", url: "/virtual", waitFor: null },
  { name: "research.png", url: "/research", waitFor: null },
];

async function getConfig() {
  const res = await fetch(`${BACKEND}/config`);
  if (!res.ok) throw new Error(`GET /config failed: ${res.status}`);
  return res.json();
}

async function setConfig(payload) {
  const res = await fetch(`${BACKEND}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`PUT /config failed: ${res.status}`);
}

async function shot(browser, { name, url, waitFor, viewport = { width: 1440, height: 900 } }) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  try {
    await page.goto(`${FRONTEND}${url}`, { waitUntil: "networkidle", timeout: 20000 });
    if (waitFor) {
      await page.getByText(waitFor).first().waitFor({ timeout: 15000 });
    } else {
      await page.waitForTimeout(1500);
    }
    await page.waitForTimeout(300);

    const bodyText = await page.locator("body").innerText();
    const marker = FAILURE_MARKERS.find((m) => bodyText.includes(m));
    if (marker) {
      console.warn(`skipped ${name}: page shows "${marker}" instead of real content`);
      return false;
    }

    await page.screenshot({ path: path.join(outDir, name), fullPage: false });
    console.log(`saved ${name}`);
    return true;
  } catch (err) {
    console.warn(`skipped ${name}: ${err.message.split("\n")[0]}`);
    return false;
  } finally {
    await context.close();
  }
}

async function main() {
  // Read current settings so this run restores them exactly, rather than
  // assuming a default -- a developer with reports already enabled, or a
  // different local login override set, should see their config unchanged
  // after this script runs.
  const before = await getConfig();
  const originalReportsTab = before.tabs?.reports ?? false;
  const originalLocalLoginEmail = before.local_login_email ?? null;

  const results = [];

  // Everything from here on mutates config.yaml (local_login_email, and per-
  // page tab overrides), so it all lives inside this try/finally -- a crash
  // anywhere below (chromium failing to launch, a setConfig network error,
  // etc.) must still trigger the restore, not just a clean loop completion.
  try {
    // Several admin/settings pages 404 into an auth-wall unless a local
    // login identity is configured (auth.disable_auth alone isn't enough).
    await setConfig({ auth: { local_login_email: OWNER } });

    const browser = await chromium.launch();
    try {
      for (const pageSpec of PAGES) {
        if (pageSpec.requiresConfig) {
          try {
            await setConfig(pageSpec.requiresConfig);
            const ok = await shot(browser, pageSpec);
            results.push({ name: pageSpec.name, ok });
          } finally {
            await setConfig({ ui: { tabs: { reports: originalReportsTab } } });
          }
        } else {
          const ok = await shot(browser, pageSpec);
          results.push({ name: pageSpec.name, ok });
        }
      }
    } finally {
      await browser.close();
    }
  } finally {
    // GET /config normalizes an empty-string override to null, so restoring
    // with that raw value would write a literal `null` into config.yaml
    // instead of the repo's `''` convention for "no override" -- coerce back.
    await setConfig({ auth: { local_login_email: originalLocalLoginEmail ?? "" } });
  }

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} screenshots captured.`);
  if (failed.length) {
    console.log(`Skipped: ${failed.map((f) => f.name).join(", ")}`);
  }
}

await main();
