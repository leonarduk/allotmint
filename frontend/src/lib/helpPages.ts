// Shared "what each page does" copy (#7434). The Help page renders the full
// list; the dashboard's first-run banner (#7827) reuses a few entries so the
// two never drift apart.
import { isModeEnabled } from '../pageManifest';
import type { Mode } from '../modes';
import type { TabsConfig } from '../ConfigContext';

export interface HelpPageEntry {
  path: string;
  // The registry mode gating this page (frontend/src/routes/registry.ts).
  // Entries are filtered through isModeEnabled() below so a deployment that
  // disables a tab (e.g. this repo's own config.yaml disables transactions/
  // reports/taxtools) never shows a dead link here (#7226).
  mode: Mode;
  titleKey: string;
  titleDefault: string;
  descriptionKey: string;
  descriptionDefault: string;
}

export const HELP_PAGES: HelpPageEntry[] = [
  {
    path: '/',
    mode: 'group',
    // Not app.modes.group ("Group") -- this page is titled "Dashboard" in
    // its own right, so it needs a dedicated key rather than one that
    // already resolves to different text.
    titleKey: 'help.pages.dashboardTitle',
    titleDefault: 'Dashboard',
    descriptionKey: 'help.pages.group',
    descriptionDefault:
      'The main overview: combined holdings, values and allocation across the owners in the selected group.',
  },
  {
    path: '/market',
    mode: 'market',
    titleKey: 'app.modes.market',
    titleDefault: 'Market Overview',
    descriptionKey: 'help.pages.market',
    descriptionDefault: 'A snapshot of overall market conditions and indices.',
  },
  {
    path: '/movers',
    mode: 'movers',
    titleKey: 'app.modes.movers',
    titleDefault: 'Movers',
    descriptionKey: 'help.pages.movers',
    descriptionDefault:
      'The instruments in your portfolios that moved the most, up or down.',
  },
  {
    path: '/instrument',
    mode: 'instrument',
    titleKey: 'app.modes.instrument',
    titleDefault: 'Sector Analysis',
    descriptionKey: 'help.pages.instrument',
    descriptionDefault: 'Detail and price history for a single instrument.',
  },
  {
    path: '/performance',
    mode: 'performance',
    titleKey: 'app.modes.performance',
    titleDefault: 'Performance',
    descriptionKey: 'help.pages.performance',
    descriptionDefault:
      'Returns over time for an owner, compared against a benchmark.',
  },
  {
    path: '/input',
    mode: 'transactions',
    titleKey: 'app.modes.transactions',
    titleDefault: 'Transactions',
    descriptionKey: 'help.pages.transactions',
    descriptionDefault:
      'Record buys, sells and other transactions, or import them from a CSV.',
  },
  {
    path: '/dividends',
    mode: 'dividends',
    titleKey: 'app.modes.dividends',
    titleDefault: 'Dividends',
    descriptionKey: 'help.pages.dividends',
    descriptionDefault:
      'Dividend income received, by tax year, year or month and by holding, with a trailing-12-month total.',
  },
  {
    path: '/trading',
    mode: 'trading',
    titleKey: 'help.pages.signalsTitle',
    titleDefault: 'Ideas: Signals',
    descriptionKey: 'help.pages.trading',
    descriptionDefault:
      'Buy and sell candidates among the instruments you hold, from fixed momentum and risk rules set on the server. Informational, not trade instructions.',
  },
  {
    path: '/screener',
    mode: 'screener',
    titleKey: 'help.pages.screenTitle',
    titleDefault: 'Ideas: Screen',
    descriptionKey: 'help.pages.screener',
    descriptionDefault:
      'Filter any watchlist or list of tickers by fundamentals such as P/E, margins, leverage or dividend yield.',
  },
  {
    path: '/watchlist',
    mode: 'watchlist',
    titleKey: 'app.modes.watchlist',
    titleDefault: 'Watchlist',
    descriptionKey: 'help.pages.watchlist',
    descriptionDefault: "Track instruments you don't currently hold.",
  },
  {
    path: '/allocation',
    mode: 'allocation',
    titleKey: 'app.modes.allocation',
    titleDefault: 'Allocation',
    descriptionKey: 'help.pages.allocation',
    descriptionDefault:
      'How your holdings are split by asset class, sector and region.',
  },
  {
    path: '/strategy',
    mode: 'rebalance',
    titleKey: 'app.modes.rebalance',
    titleDefault: 'Strategy',
    descriptionKey: 'help.pages.rebalance',
    descriptionDefault:
      'Pick a target allocation from built-in or your own strategies, then see drift and the rebalancing trades to bring your portfolio back toward it.',
  },
  {
    path: '/reports',
    mode: 'reports',
    titleKey: 'app.modes.reports',
    titleDefault: 'Reports',
    descriptionKey: 'help.pages.reports',
    descriptionDefault: 'Generate and download portfolio reports.',
  },
  {
    path: '/query',
    mode: 'query',
    titleKey: 'app.modes.query',
    titleDefault: 'Custom Query',
    descriptionKey: 'help.pages.query',
    descriptionDefault:
      'Market value or gain for your own holdings over a date range, by owner and ticker, with save, share and export.',
  },
  {
    path: '/pension/forecast',
    mode: 'pension',
    titleKey: 'app.modes.pension',
    titleDefault: 'Pension Forecast',
    descriptionKey: 'help.pages.pension',
    descriptionDefault:
      'Project pension contributions and value forward in time.',
  },
  {
    path: '/tax-tools',
    mode: 'taxtools',
    titleKey: 'app.modes.taxtools',
    titleDefault: 'Tax Tools',
    descriptionKey: 'help.pages.taxtools',
    descriptionDefault:
      'Helpers for allowance usage and tax-related calculations.',
  },
  {
    path: '/research',
    mode: 'research',
    titleKey: 'app.modes.research',
    titleDefault: 'Instrument Detail',
    descriptionKey: 'help.pages.research',
    descriptionDefault: 'Deeper research tools for individual instruments.',
  },
  {
    path: '/settings',
    mode: 'settings',
    titleKey: 'app.modes.settings',
    titleDefault: 'User Settings',
    descriptionKey: 'help.pages.settings',
    descriptionDefault: 'Your profile, currency and display preferences.',
  },
  {
    path: '/alert-settings',
    mode: 'alertsettings',
    titleKey: 'app.modes.alertsettings',
    titleDefault: 'Alert Settings',
    descriptionKey: 'help.pages.alertsettings',
    descriptionDefault:
      'Configure the thresholds that trigger portfolio alerts.',
  },
];

/** HELP_PAGES entries whose tab is enabled in this deployment. */
export function visibleHelpPages(
  tabs: TabsConfig,
  disabledTabs?: readonly string[]
): HelpPageEntry[] {
  return HELP_PAGES.filter((entry) =>
    isModeEnabled(entry.mode, tabs, disabledTabs)
  );
}
