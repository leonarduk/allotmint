// Auto-generated via backend route metadata
export interface SmokeEndpoint { method: string; path: string; body?: any }
export const smokeEndpoints: SmokeEndpoint[] = [
  {
    "method": "GET",
    "path": "/account/{owner}/{account}"
  },
  {
    "method": "POST",
    "path": "/accounts/{owner}/approval-requests"
  },
  {
    "method": "DELETE",
    "path": "/accounts/{owner}/approvals"
  },
  {
    "method": "GET",
    "path": "/accounts/{owner}/approvals"
  },
  {
    "method": "POST",
    "path": "/accounts/{owner}/approvals"
  },
  {
    "method": "GET",
    "path": "/agent/stats"
  },
  {
    "method": "GET",
    "path": "/alert-thresholds/{user}"
  },
  {
    "method": "POST",
    "path": "/alert-thresholds/{user}"
  },
  {
    "method": "GET",
    "path": "/alerts/"
  },
  {
    "method": "DELETE",
    "path": "/alerts/push-subscription/{user}"
  },
  {
    "method": "POST",
    "path": "/alerts/push-subscription/{user}"
  },
  {
    "method": "GET",
    "path": "/alerts/settings/{user}"
  },
  {
    "method": "POST",
    "path": "/alerts/settings/{user}"
  },
  {
    "method": "GET",
    "path": "/api/quotes"
  },
  {
    "method": "POST",
    "path": "/compliance/validate"
  },
  {
    "method": "GET",
    "path": "/compliance/{owner}"
  },
  {
    "method": "GET",
    "path": "/config"
  },
  {
    "method": "PUT",
    "path": "/config"
  },
  {
    "method": "POST",
    "path": "/custom-query/run"
  },
  {
    "method": "GET",
    "path": "/custom-query/saved"
  },
  {
    "method": "GET",
    "path": "/custom-query/{slug}"
  },
  {
    "method": "POST",
    "path": "/custom-query/{slug}"
  },
  {
    "method": "GET",
    "path": "/dividends"
  },
  {
    "method": "GET",
    "path": "/events"
  },
  {
    "method": "GET",
    "path": "/goals/"
  },
  {
    "method": "POST",
    "path": "/goals/"
  },
  {
    "method": "DELETE",
    "path": "/goals/{name}"
  },
  {
    "method": "GET",
    "path": "/goals/{name}"
  },
  {
    "method": "PUT",
    "path": "/goals/{name}"
  },
  {
    "method": "GET",
    "path": "/groups"
  },
  {
    "method": "GET",
    "path": "/health"
  },
  {
    "method": "GET",
    "path": "/instrument/"
  },
  {
    "method": "GET",
    "path": "/instrument/admin"
  },
  {
    "method": "DELETE",
    "path": "/instrument/admin/{exchange}/{ticker}"
  },
  {
    "method": "GET",
    "path": "/instrument/admin/{exchange}/{ticker}"
  },
  {
    "method": "POST",
    "path": "/instrument/admin/{exchange}/{ticker}"
  },
  {
    "method": "PUT",
    "path": "/instrument/admin/{exchange}/{ticker}"
  },
  {
    "method": "GET",
    "path": "/instrument/search"
  },
  {
    "method": "GET",
    "path": "/logs"
  },
  {
    "method": "GET",
    "path": "/market/overview"
  },
  {
    "method": "GET",
    "path": "/metrics/{owner}"
  },
  {
    "method": "GET",
    "path": "/movers"
  },
  {
    "method": "GET",
    "path": "/news"
  },
  {
    "method": "GET",
    "path": "/nudges/"
  },
  {
    "method": "POST",
    "path": "/nudges/snooze"
  },
  {
    "method": "POST",
    "path": "/nudges/subscribe"
  },
  {
    "method": "GET",
    "path": "/owners"
  },
  {
    "method": "GET",
    "path": "/pension/forecast"
  },
  {
    "method": "GET",
    "path": "/performance-group/{slug}/alpha"
  },
  {
    "method": "GET",
    "path": "/performance-group/{slug}/max-drawdown"
  },
  {
    "method": "GET",
    "path": "/performance-group/{slug}/tracking-error"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/alpha"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/holdings"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/max-drawdown"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/tracking-error"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/twr"
  },
  {
    "method": "GET",
    "path": "/performance/{owner}/xirr"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}/instrument/{ticker}"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}/instruments"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}/movers"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}/regions"
  },
  {
    "method": "GET",
    "path": "/portfolio-group/{slug}/sectors"
  },
  {
    "method": "GET",
    "path": "/portfolio/{owner}"
  },
  {
    "method": "GET",
    "path": "/prices/refresh"
  },
  {
    "method": "POST",
    "path": "/prices/refresh"
  },
  {
    "method": "GET",
    "path": "/quests/today"
  },
  {
    "method": "POST",
    "path": "/quests/{quest_id}/complete"
  },
  {
    "method": "GET",
    "path": "/returns/compare"
  },
  {
    "method": "GET",
    "path": "/scenario"
  },
  {
    "method": "GET",
    "path": "/scenario/historical"
  },
  {
    "method": "GET",
    "path": "/screener/"
  },
  {
    "method": "POST",
    "path": "/support/portfolio-health"
  },
  {
    "method": "POST",
    "path": "/support/telegram"
  },
  {
    "method": "GET",
    "path": "/tax/allowances"
  },
  {
    "method": "POST",
    "path": "/tax/harvest"
  },
  {
    "method": "GET",
    "path": "/timeseries/admin"
  },
  {
    "method": "POST",
    "path": "/timeseries/admin/{ticker}/{exchange}/rebuild_cache"
  },
  {
    "method": "POST",
    "path": "/timeseries/admin/{ticker}/{exchange}/refetch"
  },
  {
    "method": "GET",
    "path": "/timeseries/edit"
  },
  {
    "method": "POST",
    "path": "/timeseries/edit"
  },
  {
    "method": "GET",
    "path": "/timeseries/html"
  },
  {
    "method": "GET",
    "path": "/timeseries/meta"
  },
  {
    "method": "POST",
    "path": "/token"
  },
  {
    "method": "POST",
    "path": "/token/google"
  },
  {
    "method": "GET",
    "path": "/trading-agent/signals"
  },
  {
    "method": "GET",
    "path": "/transactions"
  },
  {
    "method": "POST",
    "path": "/transactions"
  },
  {
    "method": "GET",
    "path": "/transactions/compliance"
  },
  {
    "method": "POST",
    "path": "/transactions/import"
  },
  {
    "method": "GET",
    "path": "/user-config/{owner}"
  },
  {
    "method": "POST",
    "path": "/user-config/{owner}"
  },
  {
    "method": "GET",
    "path": "/v1/models"
  },
  {
    "method": "GET",
    "path": "/var/{owner}"
  },
  {
    "method": "GET",
    "path": "/var/{owner}/breakdown"
  },
  {
    "method": "POST",
    "path": "/var/{owner}/recompute"
  },
  {
    "method": "GET",
    "path": "/virtual-portfolios"
  },
  {
    "method": "POST",
    "path": "/virtual-portfolios"
  },
  {
    "method": "DELETE",
    "path": "/virtual-portfolios/{vp_id}"
  },
  {
    "method": "GET",
    "path": "/virtual-portfolios/{vp_id}"
  }
] as const;

export function fillPath(path: string): string {
  return path.replace(/\{[^}]+\}/g, 'test');
}

export async function runSmoke(base: string) {
  for (const ep of smokeEndpoints) {
    const url = base + fillPath(ep.path);
    const res = await fetch(url, { method: ep.method, body: ep.body ? JSON.stringify(ep.body) : undefined, headers: ep.body ? { 'Content-Type': 'application/json' } : undefined });
    if (res.status >= 500) {
      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);
    }
  }
}

if (require.main === module) {
  runSmoke(process.argv[2] || process.env.SMOKE_URL || 'http://localhost:8000').catch(err => { console.error(err); process.exit(1); });
}
