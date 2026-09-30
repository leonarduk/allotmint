// Refreshes docs/assets/qa-screenshots/*.png against the repo's own bundled
// demo dataset (data/accounts/demo-owner, data/accounts/alice) instead of a
// real private data checkout, so these images are safe to commit to a public
// repo and don't depend on any contributor's personal data.
//
// Requires the local dev servers already running:
//   DATA_ROOT=data bash scripts/bash/run-local-api.sh   (backend)
//   npm run dev                                         (frontend, :2568)
//
// Usage: node frontend/scripts/capture-qa-screenshots.mjs
// Not wired into CI -- run manually before a release / whenever the UI
// changes enough that the docs screenshots look stale.
//
// Also supports a "demo walkthrough" mode that produces a shareable,
// offline-friendly set of annotated screenshots for the interview/demo
// flow (Cognito hosted-UI login -> portfolio dashboard -> one drill-down).
// This is the fallback for when the room has no reliable network/VPN access
// to click through a live app or localhost:
//
//   node frontend/scripts/capture-qa-screenshots.mjs --demo
//
// The demo run writes to docs/assets/qa-screenshots/demo/ (same committed
// convention as the rest of this directory) and emits a self-contained
// index.html so the whole walkthrough can be opened from disk with no
// network access. See docs/assets/qa-screenshots/README.md.
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../../docs/assets/qa-screenshots");
const demoOutDir = path.join(outDir, "demo");

// Local dev instances (e.g. separate worktrees/clones) each run their own
// backend on a port chosen by scripts/bash/run-local-api.sh or
// scripts/run-backend.ps1, recorded in .local/ports/backend.port at the
// repo root. Mirrors the same lookup in frontend/vite.config.ts (see #5760)
// so this script talks to the right backend instead of assuming :6468 is
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

const BACKEND = `http://localhost:${readLocalBackendPort() ?? "6468"}`;
const FRONTEND = "http://localhost:2568";
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

// The demo walkthrough: a short, ordered set of steps that mirrors the
// interview flow (login -> dashboard -> one drill-down). Each step is
// captured as an annotated PNG plus a caption, and the whole set is wrapped
// in a self-contained index.html so it can be presented offline.
//
// `login` is captured against the Cognito hosted UI when it is reachable;
// when it isn't (no network/VPN, or auth disabled locally) the step is
// skipped and the walkthrough starts at the dashboard, which is the whole
// point of having this fallback.
const DEMO_STEPS = [
  {
    name: "01-login.png",
    caption: "Sign in via the Cognito hosted UI.",
    kind: "login",
  },
  {
    name: "02-dashboard.png",
    caption: "Portfolio dashboard: merged view across all accounts.",
    url: `/?group=all`,
    waitFor: "At a glance",
  },
  {
    name: "03-portfolio.png",
    caption: "Portfolio view for the demo owner.",
    url: `/portfolio/${OWNER}`,
    waitFor: "VWRL.L",
  },
  {
    name: "04-drilldown.png",
    caption: "Drill-down: a single holding's detail.",
    url: `/portfolio/${OWNER}`,
    waitFor: "VWRL.L",
    // Click the first holding row to open its detail view before capturing.
    drilldown: true,
  },
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

// True only when the URL's parsed hostname is the Cognito hosted UI (or a
// subdomain of it). Compares the hostname, not a substring of the whole URL,
// so e.g. https://evil.example/?x=amazoncognito.com doesn't match.
function isHostedLoginUrl(rawUrl) {
  try {
    const { hostname } = new URL(rawUrl);
    return hostname === "amazoncognito.com" || hostname.endsWith(".amazoncognito.com");
  } catch {
    return false;
  }
}

// Capture one demo-walkthrough step into demoOutDir. Returns the step's
// caption on success, or null if the step was skipped (e.g. the login page
// wasn't reachable). Never throws -- a skipped step just drops out of the
// walkthrough rather than failing the whole run.
async function demoShot(browser, step) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  try {
    if (step.kind === "login") {
      // The Cognito hosted UI lives on a different origin and is only
      // reachable when auth is enabled and the network allows it. Try it,
      // but treat any failure as "skip this step" -- the walkthrough is
      // still useful without it.
      try {
        await page.goto(`${FRONTEND}/`, { waitUntil: "networkidle", timeout: 15000 });
        // If the app redirected to a hosted-UI login page, capture that.
        if (!isHostedLoginUrl(page.url())) {
          console.warn(`skipped ${step.name}: no hosted-UI login page reached`);
          return null;
        }
        await page.waitForTimeout(500);
      } catch (err) {
        console.warn(`skipped ${step.name}: ${err.message.split("\n")[0]}`);
        return null;
      }
    } else {
      await page.goto(`${FRONTEND}${step.url}`, { waitUntil: "networkidle", timeout: 20000 });
      if (step.waitFor) {
        await page.getByText(step.waitFor).first().waitFor({ timeout: 15000 });
      } else {
        await page.waitForTimeout(1500);
      }
      if (step.drilldown) {
        // Open the first holding row to reach the detail view. Best-effort:
        // if the row isn't clickable, capture the list view instead.
        try {
          const row = page.locator("table tbody tr", { hasText: step.waitFor }).first();
          await row.click({ timeout: 5000 });
          await page.waitForTimeout(800);
        } catch {
          console.warn(`${step.name}: no drill-down row clickable, capturing list view`);
        }
      }
      await page.waitForTimeout(300);

      const bodyText = await page.locator("body").innerText();
      const marker = FAILURE_MARKERS.find((m) => bodyText.includes(m));
      if (marker) {
        console.warn(`skipped ${step.name}: page shows "${marker}" instead of real content`);
        return null;
      }
    }

    await page.screenshot({ path: path.join(demoOutDir, step.name), fullPage: false });
    console.log(`saved demo/${step.name}`);
    return step.caption;
  } catch (err) {
    console.warn(`skipped ${step.name}: ${err.message.split("\n")[0]}`);
    return null;
  } finally {
    await context.close();
  }
}

// Write a self-contained index.html that presents the captured demo steps
// with their captions. Everything is referenced by relative path, so the
// folder can be opened straight from disk (file://) with no network access.
function writeDemoIndex(captured) {
  const items = captured
    .map(
      (c) => `      <figure>
        <img src="${c.name}" alt="${escapeHtml(c.caption)}" />
        <figcaption>${escapeHtml(c.caption)}</figcaption>
      </figure>`,
    )
    .join("\n");
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>AllotMint demo walkthrough</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.5rem; }
  p.lead { color: #555; }
  figure { margin: 0 0 2rem; }
  img { width: 100%; border: 1px solid #ddd; border-radius: 6px; }
  figcaption { margin-top: .5rem; font-size: .95rem; color: #333; }
</style>
</head>
<body>
  <h1>AllotMint demo walkthrough</h1>
  <p class="lead">Offline fallback for the interview flow: Cognito login &rarr; portfolio dashboard &rarr; one drill-down. Open this file directly; no network access required.</p>
${items}
</body>
</html>
`;
  fs.writeFileSync(path.join(demoOutDir, "index.html"), html);
  console.log(`saved demo/index.html (${captured.length} steps)`);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function runDemo() {
  fs.mkdirSync(demoOutDir, { recursive: true });

  const before = await getConfig();
  const originalLocalLoginEmail = before.local_login_email ?? null;

  const captured = [];
  try {
    // Same local-login override the main run needs, so the dashboard and
    // portfolio pages render real content instead of an auth wall.
    await setConfig({ auth: { local_login_email: OWNER } });

    const browser = await chromium.launch();
    try {
      for (const step of DEMO_STEPS) {
        const caption = await demoShot(browser, step);
        if (caption) captured.push({ name: step.name, caption });
      }
    } finally {
      await browser.close();
    }
  } finally {
    await setConfig({ auth: { local_login_email: originalLocalLoginEmail ?? "" } });
  }

  if (!captured.length) {
    console.warn("\nNo demo steps captured -- is the local stack running?");
    return;
  }
  writeDemoIndex(captured);
  console.log(`\n${captured.length}/${DEMO_STEPS.length} demo steps captured into docs/assets/qa-screenshots/demo/.`);
  console.log("Open docs/assets/qa-screenshots/demo/index.html to present offline.");
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

if (process.argv.includes("--demo")) {
  await runDemo();
} else {
  await main();
}
