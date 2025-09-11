// Auto-generated via backend route metadata
export interface SmokeEndpoint { method: string; path: string; query?: Record<string, string>; body?: any }
export const smokeEndpoints: SmokeEndpoint[] = [
  {
    "method": "GET",
    "path": "/account/{owner}/{account}"
  },
  {
    "method": "POST",
    "path": "/accounts/{owner}/approval-requests",
    "body": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "DELETE",
    "path": "/accounts/{owner}/approvals",
    "body": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "GET",
    "path": "/accounts/{owner}/approvals"
  },
  {
    "method": "POST",
    "path": "/accounts/{owner}/approvals",
    "body": {
      "ticker": "AAPL",
      "approved_on": "1970-01-01"
    }
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
    "body": {
      "threshold": 0
    }
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
    "body": {
      "endpoint": "test",
      "keys": {}
    }
  },
  {
    "method": "GET",
    "path": "/alerts/settings/{user}"
  },
  {
    "method": "POST",
    "path": "/alerts/settings/{user}",
    "body": {
      "threshold": 0
    }
  },
  {
    "method": "GET",
    "path": "/api/quotes"
  },
  {
    "method": "POST",
    "path": "/compliance/validate",
    "body": {
      "owner": "demo-owner"
    }
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
    "body": {
      "start": "1970-01-01",
      "end": "1970-01-01"
    }
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
    "body": {
      "start": "1970-01-01",
      "end": "1970-01-01"
    }
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
    "body": {
      "name": "test",
      "target_amount": 0,
      "target_date": "1970-01-01"
    }
  },
  {
    "method": "DELETE",
    "path": "/goals/{name}"
  },
  {
    "method": "GET",
    "path": "/goals/{name}",
    "query": {
      "current_amount": "0"
    }
  },
  {
    "method": "PUT",
    "path": "/goals/{name}",
    "body": {
      "name": "test",
      "target_amount": 0,
      "target_date": "1970-01-01"
    }
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
    "path": "/instrument/",
    "query": {
      "ticker": "AAPL"
    }
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
    "path": "/movers",
    "query": {
      "tickers": "AAPL"
    }
  },
  {
    "method": "GET",
    "path": "/news",
    "query": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "GET",
    "path": "/nudges/"
  },
  {
    "method": "POST",
    "path": "/nudges/snooze",
    "body": {
      "user": "test"
    }
  },
  {
    "method": "POST",
    "path": "/nudges/subscribe",
    "body": {
      "user": "test",
      "frequency": 0
    }
  },
  {
    "method": "GET",
    "path": "/owners"
  },
  {
    "method": "GET",
    "path": "/pension/forecast",
    "query": {
      "owner": "demo-owner",
      "death_age": "0"
    }
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
    "path": "/performance/{owner}/holdings",
    "query": {
      "date": "1970-01-01"
    }
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
    "path": "/returns/compare",
    "query": {
      "owner": "demo-owner"
    }
  },
  {
    "method": "GET",
    "path": "/scenario",
    "query": {
      "ticker": "AAPL",
      "pct": "0"
    }
  },
  {
    "method": "GET",
    "path": "/scenario/historical",
    "query": {
      "horizons": "[0]"
    }
  },
  {
    "method": "GET",
    "path": "/screener/",
    "query": {
      "tickers": "AAPL"
    }
  },
  {
    "method": "POST",
    "path": "/support/portfolio-health"
  },
  {
    "method": "POST",
    "path": "/support/telegram",
    "body": {
      "text": "test"
    }
  },
  {
    "method": "GET",
    "path": "/tax/allowances"
  },
  {
    "method": "POST",
    "path": "/tax/harvest",
    "body": {
      "positions": [
        {
          "ticker": "test",
          "basis": 0,
          "price": 0
        }
      ]
    }
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
    "path": "/timeseries/edit",
    "query": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "POST",
    "path": "/timeseries/edit",
    "query": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "GET",
    "path": "/timeseries/html",
    "query": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "GET",
    "path": "/timeseries/meta",
    "query": {
      "ticker": "AAPL"
    }
  },
  {
    "method": "POST",
    "path": "/token",
    "body": {
      "id_token": "test"
    }
  },
  {
    "method": "POST",
    "path": "/token/google",
    "body": {}
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
    "body": {
      "owner": "test",
      "account": "test",
      "ticker": "test",
      "date": "1970-01-01",
      "price_gbp": 0,
      "units": 0
    }
  },
  {
    "method": "GET",
    "path": "/transactions/compliance",
    "query": {
      "owner": "demo-owner"
    }
  },
  {
    "method": "POST",
    "path": "/transactions/import",
    "body": {
      "__form__": {
        "provider": "test",
        "file": "__file__"
      }
    }
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
    "path": "/var/{owner}/recompute"
  },
  {
    "method": "GET",
    "path": "/virtual-portfolios"
  },
  {
    "method": "POST",
    "path": "/virtual-portfolios",
    "body": {
      "id": "test",
      "name": "test"
    }
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

// Provide sample values for path parameters so requests avoid 422/400 errors.
// Values are chosen based on common parameter names. Unknown names default to
// `1` which parses as an integer or string.
const SAMPLE_PATH_VALUES: Record<string, string> = {
  owner: 'demo-owner',
  account: 'demo-account',
  user: 'user@example.com',
  email: 'user@example.com',
  id: '1',
  vp_id: '1',
  quest_id: 'check-in',
  slug: 'demo-slug',
  name: 'demo',
  exchange: 'NASDAQ',
  ticker: 'AAPL',
};

export function fillPath(path: string): string {
  return path.replace(/\{([^}]+)\}/g, (_, key: string) => {
    const k = key.toLowerCase();
    if (SAMPLE_PATH_VALUES[k]) return SAMPLE_PATH_VALUES[k];
    if (k.includes('email')) return 'user@example.com';
    if (k.includes('id')) return '1';
    if (k.includes('user')) return 'user@example.com';
    if (k.includes('date')) return '1970-01-01';
    return '1';
  });
}

export async function runSmoke(base: string) {
  for (const ep of smokeEndpoints) {
    let url = base + fillPath(ep.path);
    if (ep.query) url += '?' + new URLSearchParams(ep.query).toString();
    let body: any = undefined;
    let headers: any = undefined;
    if (ep.body !== undefined) {
      if ((ep.body as any).__form__) {
        const fd = new FormData();
        for (const [k, v] of Object.entries((ep.body as any).__form__)) {
          fd.set(k, v === '__file__' ? new Blob(['test']) : (v as any));
        }
        body = fd;
      } else if (ep.body instanceof FormData) {
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
