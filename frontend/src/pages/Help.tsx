import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SectionCard from "../components/SectionCard";
import { useConfig } from "../ConfigContext";
import { isModeEnabled } from "../pageManifest";
import type { Mode } from "../modes";

// Default issue tracker URL used when VITE_ISSUE_TRACKER_URL is not set.
// Deployments using a different tracker (Jira, GitLab, self-hosted, ...) can
// override this via the environment variable without code changes.
const DEFAULT_ISSUES_URL = "https://github.com/leonarduk/allotmint/issues/new";

// Vite exposes env vars prefixed with VITE_ on import.meta.env. Fall back to
// the default when the variable is unset or empty so the link is never
// undefined.
const ISSUES_URL =
  (import.meta.env.VITE_ISSUE_TRACKER_URL as string | undefined)?.trim() ||
  DEFAULT_ISSUES_URL;

interface HelpPageEntry {
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

const HELP_PAGES: HelpPageEntry[] = [
  {
    path: "/",
    mode: "group",
    // Not app.modes.group ("Group") -- this page is titled "Dashboard" in
    // its own right, so it needs a dedicated key rather than one that
    // already resolves to different text.
    titleKey: "help.pages.dashboardTitle",
    titleDefault: "Dashboard",
    descriptionKey: "help.pages.group",
    descriptionDefault:
      "The main overview: combined holdings, values and allocation across the owners in the selected group.",
  },
  {
    path: "/market",
    mode: "market",
    titleKey: "app.modes.market",
    titleDefault: "Market Overview",
    descriptionKey: "help.pages.market",
    descriptionDefault: "A snapshot of overall market conditions and indices.",
  },
  {
    path: "/movers",
    mode: "movers",
    titleKey: "app.modes.movers",
    titleDefault: "Movers",
    descriptionKey: "help.pages.movers",
    descriptionDefault: "The instruments in your portfolios that moved the most, up or down.",
  },
  {
    path: "/instrument",
    mode: "instrument",
    titleKey: "app.modes.instrument",
    titleDefault: "Sector Analysis",
    descriptionKey: "help.pages.instrument",
    descriptionDefault: "Detail and price history for a single instrument.",
  },
  {
    path: "/performance",
    mode: "performance",
    titleKey: "app.modes.performance",
    titleDefault: "Performance",
    descriptionKey: "help.pages.performance",
    descriptionDefault: "Returns over time for an owner, compared against a benchmark.",
  },
  {
    path: "/input",
    mode: "transactions",
    titleKey: "app.modes.transactions",
    titleDefault: "Transactions",
    descriptionKey: "help.pages.transactions",
    descriptionDefault: "Record buys, sells and other transactions, or import them from a CSV.",
  },
  {
    path: "/dividends",
    mode: "dividends",
    titleKey: "app.modes.dividends",
    titleDefault: "Dividends",
    descriptionKey: "help.pages.dividends",
    descriptionDefault:
      "Dividend income received, by tax year, year or month and by holding, with a trailing-12-month total.",
  },
  {
    path: "/trading",
    mode: "trading",
    titleKey: "help.pages.signalsTitle",
    titleDefault: "Ideas: Signals",
    descriptionKey: "help.pages.trading",
    descriptionDefault:
      "Buy and sell candidates among the instruments you hold, from fixed momentum and risk rules set on the server. Informational, not trade instructions.",
  },
  {
    path: "/screener",
    mode: "screener",
    titleKey: "help.pages.screenTitle",
    titleDefault: "Ideas: Screen",
    descriptionKey: "help.pages.screener",
    descriptionDefault:
      "Filter any watchlist or list of tickers by fundamentals such as P/E, margins, leverage or dividend yield.",
  },
  {
    path: "/watchlist",
    mode: "watchlist",
    titleKey: "app.modes.watchlist",
    titleDefault: "Watchlist",
    descriptionKey: "help.pages.watchlist",
    descriptionDefault: "Track instruments you don't currently hold.",
  },
  {
    path: "/allocation",
    mode: "allocation",
    titleKey: "app.modes.allocation",
    titleDefault: "Allocation",
    descriptionKey: "help.pages.allocation",
    descriptionDefault: "How your holdings are split by asset class, sector and region.",
  },
  {
    path: "/strategy",
    mode: "rebalance",
    titleKey: "app.modes.rebalance",
    titleDefault: "Strategy",
    descriptionKey: "help.pages.rebalance",
    descriptionDefault:
      "Pick a target allocation from built-in or your own strategies, then see drift and the rebalancing trades to bring your portfolio back toward it.",
  },
  {
    path: "/reports",
    mode: "reports",
    titleKey: "app.modes.reports",
    titleDefault: "Reports",
    descriptionKey: "help.pages.reports",
    descriptionDefault: "Generate and download portfolio reports.",
  },
  {
    path: "/query",
    mode: "query",
    titleKey: "app.modes.query",
    titleDefault: "Custom Query",
    descriptionKey: "help.pages.query",
    descriptionDefault:
      "Market value or gain for your own holdings over a date range, by owner and ticker, with save, share and export.",
  },
  {
    path: "/pension/forecast",
    mode: "pension",
    titleKey: "app.modes.pension",
    titleDefault: "Pension Forecast",
    descriptionKey: "help.pages.pension",
    descriptionDefault: "Project pension contributions and value forward in time.",
  },
  {
    path: "/tax-tools",
    mode: "taxtools",
    titleKey: "app.modes.taxtools",
    titleDefault: "Tax Tools",
    descriptionKey: "help.pages.taxtools",
    descriptionDefault: "Helpers for allowance usage and tax-related calculations.",
  },
  {
    path: "/research",
    mode: "research",
    titleKey: "app.modes.research",
    titleDefault: "Instrument Detail",
    descriptionKey: "help.pages.research",
    descriptionDefault: "Deeper research tools for individual instruments.",
  },
  {
    path: "/settings",
    mode: "settings",
    titleKey: "app.modes.settings",
    titleDefault: "User Settings",
    descriptionKey: "help.pages.settings",
    descriptionDefault: "Your profile, currency and display preferences.",
  },
  {
    path: "/alert-settings",
    mode: "alertsettings",
    titleKey: "app.modes.alertsettings",
    titleDefault: "Alert Settings",
    descriptionKey: "help.pages.alertsettings",
    descriptionDefault: "Configure the thresholds that trigger portfolio alerts.",
  },
];

export default function Help() {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const visiblePages = HELP_PAGES.filter((entry) =>
    isModeEnabled(entry.mode, tabs, disabledTabs),
  );

  return (
    <div className="container mx-auto max-w-3xl space-y-8 p-4">
      <header>
        <h1 className="mb-1 text-2xl font-bold md:text-4xl">
          {t("help.title", "Help & Getting Started")}
        </h1>
        <p className="text-sm text-gray-600">
          {t(
            "help.intro",
            "A quick guide to what each page in AllotMint is for, plus how to look up unfamiliar terms and how to report a problem.",
          )}
        </p>
      </header>

      <SectionCard
        title={t("help.pagesTitle", "What each page does")}
        defaultOpen
      >
        <dl className="space-y-3">
          {visiblePages.map((entry) => (
            <div key={entry.path}>
              <dt>
                <Link
                  to={entry.path}
                  className="font-medium text-blue-600 hover:underline"
                >
                  {t(entry.titleKey, entry.titleDefault)}
                </Link>
              </dt>
              <dd className="text-sm text-gray-600">
                {t(entry.descriptionKey, entry.descriptionDefault)}
              </dd>
            </div>
          ))}
        </dl>
      </SectionCard>

      <SectionCard title={t("help.glossaryTitle", "Metrics glossary")} defaultOpen>
        <p className="text-sm text-gray-600">
          {t(
            "help.glossaryDescription",
            "Not sure what a metric like Sharpe ratio, max drawdown or tracking error means? The glossary explains the terms used throughout the app.",
          )}
        </p>
        <Link
          to="/metrics-explained"
          className="mt-2 inline-block rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          {t("help.glossaryLink", "Open the metrics glossary")}
        </Link>
      </SectionCard>

      <SectionCard title={t("help.reportTitle", "Report a problem")} defaultOpen>
        <p className="text-sm text-gray-600">
          {t(
            "help.reportDescription",
            "Found a bug or something confusing? Let us know on GitHub so it can be tracked and fixed.",
          )}
        </p>
        <a
          href={ISSUES_URL}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-block rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          {t("help.reportLink", "Open a GitHub issue")}
        </a>
      </SectionCard>
    </div>
  );
}
