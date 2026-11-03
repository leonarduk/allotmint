import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useConfig } from '@/ConfigContext';
import {
  ROUTE_REGISTRY,
  getMenuEntries,
  standalonePageRoutes,
} from '@/routes/registry';
import { SUPPORT_TABS, USER_TABS } from '@/tabPlugins';

/*
 * Free-build baseline for the frontend plugin extension point (#6836, ADR
 * docs/decisions/6836-pro-frontend-plugin-packaging.md §7). These snapshots
 * were captured BEFORE `virtual:allotmint-plugins` was wired into the page
 * manifest and ConfigContext. With no plugins configured (the public build,
 * ALLOTMINT_PLUGIN_ENTRIES unset) they must not change: if one does, free
 * behaviour changed. Never update them as part of plugin-host work.
 */

const sampleContext = { owner: 'alice', group: 'kids' };

describe('free build (no frontend plugins)', () => {
  it('keeps the route table unchanged', () => {
    const table = ROUTE_REGISTRY.map((entry) =>
      [
        entry.mode,
        entry.routeSegment ?? '-',
        entry.section,
        entry.menuCategory ?? '-',
        entry.priority ?? '-',
        entry.hideFromMenu ? 'hidden' : '-',
        entry.menuMergedInto ?? '-',
        entry.menuLabelKey ?? '-',
        entry.routePath ?? '-',
        entry.lazyComponent ? 'lazy' : '-',
        entry.defaultPath({}),
        entry.defaultPath(sampleContext),
      ].join(' | '),
    );
    expect(table).toMatchInlineSnapshot(`
      [
        "group | - | user | dashboard | 0 | - | - | - | - | - | /?group=all | /?group=kids",
        "plot | plot | user | dashboard | 3 | - | - | - | /plot/* | lazy | /plot | /plot",
        "market | market | user | dashboard | 5 | - | - | - | - | - | /market | /market",
        "movers | movers | user | dashboard | 10 | - | - | - | - | - | /movers | /movers",
        "instrument | instrument | user | dashboard | 6 | - | - | - | - | - | /instrument | /instrument/kids",
        "owner | portfolio | user | dashboard | 30 | hidden | - | - | - | - | /portfolio | /?owner=alice",
        "performance | performance | user | dashboard | 40 | - | - | - | - | - | /performance | /performance/alice",
        "transactions | transactions | user | dashboard | 25 | - | - | - | - | - | /transactions | /transactions",
        "dividends | dividends | user | dashboard | 26 | - | - | - | /dividends | lazy | /dividends | /dividends",
        "riskreturn | returns-volatility | user | dashboard | 42 | - | - | - | /returns-volatility | lazy | /returns-volatility | /returns-volatility",
        "trading | trading | user | insights | 55 | - | - | ideas | - | - | /trading | /trading",
        "screener | screener | user | insights | 60 | - | trading | - | - | - | /screener | /screener",
        "timeseries | timeseries | support | operations | 70 | - | - | - | - | - | /timeseries | /timeseries",
        "watchlist | watchlist | user | insights | 80 | - | trading | - | - | - | /watchlist | /watchlist",
        "allocation | allocation | user | dashboard | 85 | - | - | - | - | - | /allocation | /allocation",
        "instrumentadmin | instrumentadmin | support | operations | 85 | - | - | - | - | - | /instrumentadmin | /instrumentadmin",
        "rebalance | strategy | user | insights | 86 | - | - | - | - | - | /strategy | /strategy",
        "dataadmin | dataadmin | support | operations | 90 | - | - | - | - | - | /dataadmin | /dataadmin",
        "dataquality | data-quality | support | operations | 91 | - | - | - | /data-quality | lazy | /data-quality | /data-quality",
        "awscosts | aws-costs | support | operations | 92 | - | - | - | /aws-costs | lazy | /aws-costs | /aws-costs",
        "dataexplorer | data-explorer | support | operations | 92 | - | - | - | /data-explorer | lazy | /data-explorer | /data-explorer",
        "reports | reports | user | dashboard | 100 | - | - | - | - | - | /reports | /reports",
        "query | query | user | dashboard | 101 | - | - | - | - | - | /query | /query",
        "trail | trail | user | goals | 102 | - | - | - | /trail | lazy | /trail | /trail",
        "alerts | alerts | standalone | - | 103 | - | - | - | - | - | /alerts | /alerts",
        "alertsettings | alert-settings | user | preferences | 104 | - | - | - | /alert-settings | lazy | /alert-settings | /alert-settings",
        "settings | settings | user | preferences | 105 | - | - | - | - | - | /settings | /settings",
        "pension | pension | user | goals | 107 | - | - | - | - | - | /pension/forecast | /pension/forecast",
        "taxtools | tax-tools | user | goals | 108 | - | - | - | - | - | /tax-tools | /tax-tools",
        "trade-compliance | trade-compliance | user | goals | 110 | - | - | - | /trade-compliance | lazy | /trade-compliance | /trade-compliance",
        "support | support | support | operations | 110 | - | - | - | /support | lazy | /support | /support",
        "help | help | user | preferences | 106 | - | - | - | /help | lazy | /help | /help",
        "scenario | scenario | user | insights | 120 | - | - | - | - | - | /scenario | /scenario",
        "virtual | virtual | standalone | - | 130 | - | - | - | /virtual | lazy | /virtual | /virtual",
        "research | research | user | insights | 140 | - | - | - | - | - | /research | /research",
        "bots | bots | user | insights | 141 | - | - | - | /bots | lazy | /bots | /bots",
        "createaccount | create-account | standalone | - | 150 | - | - | - | /create-account | lazy | /create-account | /create-account",
      ]
    `);
  });

  it('keeps the mounted standalone routes unchanged', () => {
    expect(standalonePageRoutes.map((entry) => entry.routePath)).toMatchInlineSnapshot(`
      [
        "/plot/*",
        "/dividends",
        "/returns-volatility",
        "/data-quality",
        "/aws-costs",
        "/data-explorer",
        "/trail",
        "/alert-settings",
        "/trade-compliance",
        "/support",
        "/help",
        "/virtual",
        "/bots",
        "/create-account",
      ]
    `);
  });

  it('keeps the navigation order unchanged', () => {
    expect({
      user: getMenuEntries('user').map((entry) => entry.mode),
      support: getMenuEntries('support').map((entry) => entry.mode),
      userTabs: USER_TABS,
      supportTabs: SUPPORT_TABS,
    }).toMatchInlineSnapshot(`
      {
        "support": [
          "timeseries",
          "instrumentadmin",
          "dataadmin",
          "dataquality",
          "awscosts",
          "dataexplorer",
          "support",
        ],
        "supportTabs": [
          "timeseries",
          "instrumentadmin",
          "dataadmin",
          "dataquality",
          "awscosts",
          "dataexplorer",
          "support",
        ],
        "user": [
          "group",
          "plot",
          "market",
          "instrument",
          "movers",
          "transactions",
          "dividends",
          "performance",
          "riskreturn",
          "trading",
          "screener",
          "watchlist",
          "allocation",
          "rebalance",
          "reports",
          "query",
          "trail",
          "alertsettings",
          "settings",
          "help",
          "pension",
          "taxtools",
          "trade-compliance",
          "scenario",
          "research",
          "bots",
        ],
        "userTabs": [
          "group",
          "plot",
          "market",
          "movers",
          "instrument",
          "owner",
          "performance",
          "transactions",
          "dividends",
          "riskreturn",
          "trading",
          "screener",
          "watchlist",
          "allocation",
          "rebalance",
          "reports",
          "query",
          "trail",
          "alertsettings",
          "settings",
          "pension",
          "taxtools",
          "trade-compliance",
          "help",
          "scenario",
          "research",
          "bots",
        ],
      }
    `);
  });

  it('keeps the default tabs unchanged', () => {
    const { result } = renderHook(() => useConfig());
    expect(result.current.tabs).toMatchInlineSnapshot(`
      {
        "alerts": true,
        "alertsettings": true,
        "allocation": true,
        "awscosts": true,
        "bots": true,
        "dataadmin": true,
        "dataexplorer": true,
        "dataquality": true,
        "dividends": true,
        "group": true,
        "help": true,
        "instrument": true,
        "instrumentadmin": true,
        "market": true,
        "movers": true,
        "owner": true,
        "pension": true,
        "performance": true,
        "plot": true,
        "profile": false,
        "query": true,
        "rebalance": true,
        "reports": false,
        "research": true,
        "riskreturn": true,
        "scenario": true,
        "screener": true,
        "settings": true,
        "support": true,
        "taxtools": false,
        "timeseries": true,
        "trade-compliance": false,
        "trading": true,
        "trail": false,
        "transactions": true,
        "virtual": true,
        "watchlist": true,
      }
    `);
  });
});
