// Auto-generated via backend route metadata
export interface SmokeEndpoint { method: string; path: string; body?: any }
export const smokeEndpoints: SmokeEndpoint[] = [
  {
    "method": "GET",
    "path": "/account/{owner}/{account}"
  },
  {
    "method": "POST",
    "path": "/accounts/{owner}/approval-requests",
    "body": { "ticker": "TEST" }
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
    "path": "/accounts/{owner}/approvals",
    "body": { "ticker": "TEST", "approved_on": "2020-01-01" }
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
    "path": "/alert-thresholds/{user}",
    "body": { "threshold": 1 }
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
    "path": "/alerts/push-subscription/{user}",
    "body": { "endpoint": "test", "keys": {} }
  },
  {
    "method": "GET",
    "path": "/alerts/settings/{user}"
  },
  {
    "method": "POST",
    "path": "/alerts/settings/{user}",
    "body": { "threshold": 1 }
  },
  {
    "method": "GET",
    "path": "/api/quotes"
  },
  {
    "method": "POST",
    "path": "/compliance/validate",
    "body": { "owner": "test" }
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
    "path": "/config",
    "body": {}
  },
  {
    "method": "POST",
    "path": "/custom-query/run",
    "body": { "start": "2020-01-01", "end": "2020-01-02", "tickers": ["VOD.L"] }
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
    "path": "/custom-query/{slug}",
    "body": { "start": "2020-01-01", "end": "2020-01-02", "tickers": ["VOD.L"] }
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
    "path": "/goals/",
    "body": { "name": "test", "target_amount": 0, "target_date": "2020-01-01" }
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
    "path": "/goals/{name}",
    "body": { "name": "test", "target_amount": 0, "target_date": "2020-01-01" }
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
    "path": "/instrument/admin/{exchange}/{ticker}",
    "body": {}
  },
  {
    "method": "PUT",
    "path": "/instrument/admin/{exchange}/{ticker}",
    "body": {}
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
    "path": "/nudges/snooze",
    "body": { "user": "test" }
  },
  {
    "method": "POST",
    "path": "/nudges/subscribe",
    "body": { "user": "test", "frequency": 1 }
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
    "path": "/prices/refresh",
    "body": {}
  },
  {
    "method": "GET",
    "path": "/quests/today"
  },
  {
    "method": "POST",
    "path": "/quests/{quest_id}/complete",
    "body": {}
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
    "path": "/support/portfolio-health",
    "body": {}
  },
  {
    "method": "POST",
    "path": "/support/telegram",
    "body": { "text": "test" }
  },
  {
    "method": "GET",
    "path": "/tax/allowances"
  },
  {
    "method": "POST",
    "path": "/tax/harvest",
    "body": { "positions": [{ "ticker": "TEST", "basis": 0, "price": 0 }] }
  },
  {
    "method": "GET",
    "path": "/timeseries/admin"
  },
  {
    "method": "POST",
    "path": "/timeseries/admin/{ticker}/{exchange}/rebuild_cache",
    "body": {}
  },
  {
    "method": "POST",
    "path": "/timeseries/admin/{ticker}/{exchange}/refetch",
    "body": {}
  },
  {
    "method": "GET",
    "path": "/timeseries/edit"
  },
  {
    "method": "POST",
    "path": "/timeseries/edit?ticker=VOD.L",
    "body": []
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
    "path": "/token",
    "body": { "id_token": "test" }
  },
  {
    "method": "POST",
    "path": "/token/google",
    "body": { "token": "test" }
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
    "path": "/transactions",
    "body": { "owner": "test", "account": "test", "ticker": "TEST", "date": "2020-01-01", "price_gbp": 1, "units": 1, "reason": "test" }
  },
  {
    "method": "GET",
    "path": "/transactions/compliance"
  },
  {
    "method": "POST",
    "path": "/transactions/import",
    "body": (() => { const f = new FormData(); f.append('provider','degiro'); f.append('file', new Blob(['owner,account,date,ticker,type,amount_minor,price,units,fees,comments,reason_to_buy\n'], { type: 'text/csv' }), 'data.csv'); return f; })()
  },
  {
    "method": "GET",
    "path": "/user-config/{owner}"
  },
  {
    "method": "POST",
    "path": "/user-config/{owner}",
    "body": {}
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
    "path": "/var/{owner}/recompute",
    "body": {}
  },
  {
    "method": "GET",
    "path": "/virtual-portfolios"
  },
  {
    "method": "POST",
    "path": "/virtual-portfolios",
    "body": { "id": "test", "name": "test", "holdings": [] }
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
    let body: any = undefined;
    let headers: any = undefined;
    if (ep.body !== undefined) {
      if (ep.body instanceof FormData) {
        body = ep.body;
      } else {
        body = JSON.stringify(ep.body);
        headers = { 'Content-Type': 'application/json' };
      }
    }
    const res = await fetch(url, { method: ep.method, body, headers });
    if (res.status >= 500) {
      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);
    }

    // Allow 401/403 for endpoints that require roles; they still prove the route exists
    if (res.status >= 400 && res.status !== 401 && res.status !== 403) {
      throw new Error(`${ep.method} ${ep.path} -> ${res.status}`);
    }
    const tag = res.ok ? "✓" : (res.status === 401 || res.status === 403) ? "○" : "•";
    console.log(`${tag} ${ep.method} ${ep.path} (${res.status})`);

  }
}

if (require.main === module) {
  runSmoke(process.argv[2] || process.env.SMOKE_URL || 'http://localhost:8000').catch(err => { console.error(err); process.exit(1); });
}
