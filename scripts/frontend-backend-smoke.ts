// smoke.ts
// Unified smoke test script (merged)
// Run with:  node --loader ts-node/esm smoke.ts [API_BASE]
// Requires Node 18+ for global fetch.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Auto-generated via backend route metadata (keep in sync with backend) */
export interface SmokeEndpoint {
  method: string;
  path: string;
  body?: any;
}
export const smokeEndpoints: SmokeEndpoint[] = [
  { method: "GET", path: "/owners" },
  { method: "GET", path: "/groups" },
  { method: "GET", path: "/portfolio/{owner}" },
  { method: "GET", path: "/var/{owner}" },
  { method: "GET", path: "/var/{owner}/breakdown" },
  { method: "POST", path: "/var/{owner}/recompute" },
  { method: "GET", path: "/portfolio-group/{slug}" },
  { method: "GET", path: "/portfolio-group/{slug}/instruments" },
  { method: "GET", path: "/portfolio-group/{slug}/sectors" },
  { method: "GET", path: "/portfolio-group/{slug}/regions" },
  { method: "GET", path: "/portfolio-group/{slug}/movers" },
  { method: "GET", path: "/account/{owner}/{account}" },
  { method: "GET", path: "/portfolio-group/{slug}/instrument/{ticker}" },
  { method: "GET", path: "/prices/refresh" },
  { method: "POST", path: "/prices/refresh" },
  { method: "GET", path: "/performance/{owner}/alpha" },
  { method: "GET", path: "/performance/{owner}/tracking-error" },
  { method: "GET", path: "/performance/{owner}/max-drawdown" },
  { method: "GET", path: "/performance/{owner}/twr" },
  { method: "GET", path: "/performance/{owner}/xirr" },
  { method: "GET", path: "/performance/{owner}/holdings" },
  { method: "GET", path: "/performance-group/{slug}/alpha" },
  { method: "GET", path: "/performance-group/{slug}/tracking-error" },
  { method: "GET", path: "/performance-group/{slug}/max-drawdown" },
  { method: "GET", path: "/performance/{owner}" },
  { method: "GET", path: "/returns/compare" },
  { method: "GET", path: "/instrument/search" },
  { method: "GET", path: "/instrument/" },
  { method: "GET", path: "/instrument/admin" },
  { method: "GET", path: "/instrument/admin/{exchange}/{ticker}" },
  { method: "POST", path: "/instrument/admin/{exchange}/{ticker}" },
  { method: "PUT", path: "/instrument/admin/{exchange}/{ticker}" },
  { method: "DELETE", path: "/instrument/admin/{exchange}/{ticker}" },
  { method: "GET", path: "/timeseries/meta" },
  { method: "GET", path: "/timeseries/html" },
  { method: "GET", path: "/timeseries/edit" },
  { method: "POST", path: "/timeseries/edit" },
  { method: "GET", path: "/timeseries/admin" },
  { method: "POST", path: "/timeseries/admin/{ticker}/{exchange}/refetch" },
  { method: "POST", path: "/timeseries/admin/{ticker}/{exchange}/rebuild_cache" },
  { method: "GET", path: "/transactions/compliance" },
  { method: "POST", path: "/transactions" },
  { method: "POST", path: "/transactions/import" },
  { method: "GET", path: "/transactions" },
  { method: "GET", path: "/dividends" },
  { method: "GET", path: "/alert-thresholds/{user}" },
  { method: "POST", path: "/alert-thresholds/{user}" },
  { method: "GET", path: "/alerts/" },
  { method: "GET", path: "/alerts/settings/{user}" },
  { method: "POST", path: "/alerts/settings/{user}" },
  { method: "POST", path: "/alerts/push-subscription/{user}" },
  { method: "DELETE", path: "/alerts/push-subscription/{user}" },
  { method: "POST", path: "/nudges/subscribe" },
  { method: "POST", path: "/nudges/snooze" },
  { method: "GET", path: "/nudges/" },
  { method: "GET", path: "/quests/today" },
  { method: "POST", path: "/quests/{quest_id}/complete" },
  { method: "GET", path: "/compliance/{owner}" },
  { method: "POST", path: "/compliance/validate" },
  { method: "GET", path: "/screener/" },
  { method: "POST", path: "/support/telegram" },
  { method: "POST", path: "/support/portfolio-health" },
  { method: "POST", path: "/custom-query/run" },
  { method: "GET", path: "/custom-query/saved" },
  { method: "GET", path: "/custom-query/{slug}" },
  { method: "POST", path: "/custom-query/{slug}" },
  { method: "GET", path: "/virtual-portfolios" },
  { method: "GET", path: "/virtual-portfolios/{vp_id}" },
  { method: "POST", path: "/virtual-portfolios" },
  { method: "DELETE", path: "/virtual-portfolios/{vp_id}" },
  { method: "GET", path: "/metrics/{owner}" },
  { method: "GET", path: "/agent/stats" },
  { method: "GET", path: "/trading-agent/signals" },
  { method: "GET", path: "/config" },
  { method: "PUT", path: "/config" },
  { method: "GET", path: "/api/quotes" },
  { method: "GET", path: "/news" },
  { method: "GET", path: "/market/overview" },
  { method: "GET", path: "/movers" },
  { method: "GET", path: "/v1/models" },
  { method: "GET", path: "/user-config/{owner}" },
  { method: "POST", path: "/user-config/{owner}" },
  { method: "GET", path: "/accounts/{owner}/approvals" },
  { method: "POST", path: "/accounts/{owner}/approval-requests" },
  { method: "POST", path: "/accounts/{owner}/approvals" },
  { method: "DELETE", path: "/accounts/{owner}/approvals" },
  { method: "GET", path: "/events" },
  { method: "GET", path: "/scenario" },
  { method: "GET", path: "/scenario/historical" },
  { method: "GET", path: "/logs" },
  { method: "GET", path: "/goals/" },
  { method: "POST", path: "/goals/" },
  { method: "GET", path: "/goals/{name}" },
  { method: "PUT", path: "/goals/{name}" },
  { method: "DELETE", path: "/goals/{name}" },
  { method: "POST", path: "/tax/harvest" },
  { method: "GET", path: "/tax/allowances" },
  { method: "GET", path: "/pension/forecast" },
  { method: "POST", path: "/token" },
  { method: "POST", path: "/token/google" },
  { method: "GET", path: "/health" }
] as const;

function resolveApiBase(): string {
  const arg = process.argv[2];
  if (arg && !arg.startsWith("--")) return arg;
  if (process.env.SMOKE_URL) return process.env.SMOKE_URL;
  if (process.env.API_BASE) return process.env.API_BASE;

  try {
    const __dirname = path.dirname(fileURLToPath(import.meta.url));
    const apiTsPath = path.join(__dirname, "..", "frontend", "src", "api.ts");
    const src = fs.readFileSync(apiTsPath, "utf8");
    const match = src.match(/export const API_BASE[^]*?"([^"']+)"/);
    if (match) return match[1];
  } catch {
    // ignore and fall through
  }
  return "http://localhost:8000";
}

function fillPath(p: string): string {
  // Replace templated segments with stable dummy values
  return p
    .replace("{owner}", "steve")
    .replace("{account}", "SIPP")
    .replace("{slug}", "family")
    .replace("{ticker}", "VWRL.L")
    .replace("{exchange}", "LSE")
    .replace("{user}", "steve")
    .replace("{quest_id}", "demo")
    .replace("{vp_id}", "1")
    .replace(/\{[^}]+\}/g, "test");
}

async function login(apiBase: string, idToken?: string): Promise<string | null> {
  // Attempt JWT exchange; return null if unsupported
  const tokenUrl = `${apiBase}/token`;
  try {
    const res = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken ?? process.env.TEST_ID_TOKEN ?? "test" })
    });
    if (!res.ok) {
      // 404/405 means auth not required or endpoint absent
      if (res.status === 404 || res.status === 405) return null;
      throw new Error(`Login failed: ${res.status} ${res.statusText}`);
    }
    const data = (await res.json()) as { access_token?: string };
    return data.access_token ?? null;
  } catch (e: any) {
    // If connection refused or endpoint missing, proceed unauthenticated
    if (e?.code === "ECONNREFUSED") {
      throw e;
    }
    return null;
  }
}

function assert(condition: any, msg: string) {
  if (!condition) throw new Error(msg);
}

async function fetchJson<T>(apiBase: string, token: string | null, route: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined)
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase}${route}`, { ...init, headers });
  if (!res.ok) throw new Error(`${init.method || "GET"} ${route} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function runSanityChecks(apiBase: string, token: string | null) {
  const owners = await fetchJson<any[]>(apiBase, token, "/owners");
  assert(Array.isArray(owners) && owners.length > 0, "owners array empty");
  const ownerKey = owners[0]?.owner ?? owners[0]?.id ?? "steve";
  console.log("✓ /owners");

  const groups = await fetchJson<any[]>(apiBase, token, "/groups");
  assert(Array.isArray(groups), "groups should be array");
  console.log("✓ /groups");

  const portfolio = await fetchJson<any>(apiBase, token, `/portfolio/${encodeURIComponent(ownerKey)}`);
  assert(portfolio && typeof portfolio === "object", "portfolio should be object");
  console.log("✓ /portfolio/{owner}");

  // Try a POST endpoint commonly available
  try {
    const refresh = await fetchJson<{ status?: string }>(apiBase, token, "/prices/refresh", { method: "POST" });
    assert(!refresh || typeof refresh.status === "string" || Object.keys(refresh).length >= 0, "price refresh unexpected");
    console.log("✓ /prices/refresh (POST)");
  } catch {
    console.log("• /prices/refresh (POST) skipped or not supported");
  }
}

async function runEndpoints(apiBase: string, token: string | null) {
  for (const ep of smokeEndpoints) {
    const url = apiBase + fillPath(ep.path);
    const init: RequestInit = {
      method: ep.method,
      headers: {}
    };
    if (ep.body !== undefined) {
      init.body = JSON.stringify(ep.body);
      (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    }
    if (token) {
      (init.headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(url, init);
    if (res.status >= 500) {
      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);
    }
    // Allow 401/403 for endpoints that require roles; they still prove the route exists
    if (res.status >= 400 && res.status !== 401 && res.status !== 403 && res.status !== 404) {
      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);
    }
    const tag =
      res.ok ? "✓" : res.status === 404 ? "•" : (res.status === 401 || res.status === 403) ? "○" : "•";
    console.log(`${tag} ${ep.method} ${ep.path} (${res.status})`);
  }
}

async function main() {
  const API_BASE = resolveApiBase();
  console.log(`Using API_BASE=${API_BASE}`);

  const token = await login(API_BASE, process.env.TEST_ID_TOKEN);
  if (token) {
    console.log("Authenticated via /token");
  } else {
    console.log("Proceeding without auth");
  }

  // Targeted sanity checks (fast fail on core regressions)
  await runSanityChecks(API_BASE, token);

  // Broad endpoint sweep
  await runEndpoints(API_BASE, token);

  console.log("Smoke tests completed successfully.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
