// Refreshes docs/assets/qa-screenshots/*.png against the repo's own bundled
// demo dataset (data/accounts/demo-owner, data/accounts/alice) instead of a
// real private data checkout, so these images are safe to commit to a public
// repo and don't depend on any contributor's personal data.
//
// Requires the local dev servers already running on their default ports:
//   DATA_ROOT=data bash scripts/bash/run-local-api.sh   (backend, :8000)
//   npm run dev                                         (frontend, :5173)
//
// Usage: node frontend/scripts/capture-qa-screenshots.mjs
// Not wired into CI -- run manually before a release / whenever the UI
// changes enough that the docs screenshots look stale.
import { chromium } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../../docs/assets/qa-screenshots");
const BACKEND = "http://localhost:8000";
const FRONTEND = "http://localhost:5173";
const OWNER = "demo-owner";

// routeSegment/mode names match frontend/src/routes/registry.ts. `reports`
// and `transactions` are disabled by default in config.yaml -- reports is
// toggled on for the duration of this script (see main()); transactions
// stays skipped since it needs owner-scoped write context this script
// doesn't set up.
const PAGES = [
  { name: "portfolio-view.png", url: `/portfolio/${OWNER}`, waitFor: "VWRL.L" },
  { name: "mobile-portfolio-view.png", url: `/portfolio/${OWNER}`, waitFor: "VWRL.L", viewport: { width: 390, height: 844 } },
  { name: "dashboard.png", url: `/?group=all`, waitFor: "At a glance" },
  { name: "screener.png", url: "/screener", waitFor: "Run" },
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
  const browser = await chromium.launch();
  const results = [];

  for (const pageSpec of PAGES) {
    if (pageSpec.requiresConfig) {
      await setConfig(pageSpec.requiresConfig);
    }
    const ok = await shot(browser, pageSpec);
    if (pageSpec.requiresConfig) {
      // Revert immediately so a later failure can't leave the running app
      // (and its committed config.yaml, which PUT /config persists to) in a
      // non-default state.
      await setConfig({ ui: { tabs: { reports: false } } });
    }
    results.push({ name: pageSpec.name, ok });
  }

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} screenshots captured.`);
  if (failed.length) {
    console.log(`Skipped: ${failed.map((f) => f.name).join(", ")}`);
  }
}

await main();
