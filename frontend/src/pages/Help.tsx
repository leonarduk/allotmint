import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SectionCard from "../components/SectionCard";

const ISSUES_URL = "https://github.com/leonarduk/allotmint/issues/new";

interface HelpPageEntry {
  path: string;
  titleKey: string;
  titleDefault: string;
  descriptionKey: string;
  descriptionDefault: string;
}

const HELP_PAGES: HelpPageEntry[] = [
  {
    path: "/",
    titleKey: "app.modes.group",
    titleDefault: "Dashboard",
    descriptionKey: "help.pages.group",
    descriptionDefault:
      "The main overview: combined holdings, values and allocation across the owners in the selected group.",
  },
  {
    path: "/market",
    titleKey: "app.modes.market",
    titleDefault: "Market Overview",
    descriptionKey: "help.pages.market",
    descriptionDefault: "A snapshot of overall market conditions and indices.",
  },
  {
    path: "/movers",
    titleKey: "app.modes.movers",
    titleDefault: "Movers",
    descriptionKey: "help.pages.movers",
    descriptionDefault: "The instruments in your portfolios that moved the most, up or down.",
  },
  {
    path: "/instrument",
    titleKey: "app.modes.instrument",
    titleDefault: "Instrument",
    descriptionKey: "help.pages.instrument",
    descriptionDefault: "Detail and price history for a single instrument.",
  },
  {
    path: "/performance",
    titleKey: "app.modes.performance",
    titleDefault: "Performance",
    descriptionKey: "help.pages.performance",
    descriptionDefault: "Returns over time for an owner, compared against a benchmark.",
  },
  {
    path: "/input",
    titleKey: "app.modes.transactions",
    titleDefault: "Transactions",
    descriptionKey: "help.pages.transactions",
    descriptionDefault: "Record buys, sells and other transactions, or import them from a CSV.",
  },
  {
    path: "/trading",
    titleKey: "app.modes.trading",
    titleDefault: "Trading",
    descriptionKey: "help.pages.trading",
    descriptionDefault: "Place and review trades against your accounts.",
  },
  {
    path: "/screener",
    titleKey: "app.modes.screener",
    titleDefault: "Screener & Query",
    descriptionKey: "help.pages.screener",
    descriptionDefault: "Search and filter instruments by criteria such as sector, region or yield.",
  },
  {
    path: "/watchlist",
    titleKey: "app.modes.watchlist",
    titleDefault: "Watchlist",
    descriptionKey: "help.pages.watchlist",
    descriptionDefault: "Track instruments you don't currently hold.",
  },
  {
    path: "/allocation",
    titleKey: "app.modes.allocation",
    titleDefault: "Allocation",
    descriptionKey: "help.pages.allocation",
    descriptionDefault: "How your holdings are split by asset class, sector and region.",
  },
  {
    path: "/rebalance",
    titleKey: "app.modes.rebalance",
    titleDefault: "Rebalance",
    descriptionKey: "help.pages.rebalance",
    descriptionDefault: "Suggested trades to bring your allocation back toward its targets.",
  },
  {
    path: "/reports",
    titleKey: "app.modes.reports",
    titleDefault: "Reports",
    descriptionKey: "help.pages.reports",
    descriptionDefault: "Generate and download portfolio reports.",
  },
  {
    path: "/pension/forecast",
    titleKey: "app.modes.pension",
    titleDefault: "Pension Forecast",
    descriptionKey: "help.pages.pension",
    descriptionDefault: "Project pension contributions and value forward in time.",
  },
  {
    path: "/tax-tools",
    titleKey: "app.modes.taxtools",
    titleDefault: "Tax Tools",
    descriptionKey: "help.pages.taxtools",
    descriptionDefault: "Helpers for allowance usage and tax-related calculations.",
  },
  {
    path: "/research",
    titleKey: "app.modes.research",
    titleDefault: "Research",
    descriptionKey: "help.pages.research",
    descriptionDefault: "Deeper research tools for individual instruments.",
  },
  {
    path: "/settings",
    titleKey: "app.modes.settings",
    titleDefault: "User Settings",
    descriptionKey: "help.pages.settings",
    descriptionDefault: "Your profile, currency and display preferences.",
  },
  {
    path: "/alert-settings",
    titleKey: "app.modes.alertsettings",
    titleDefault: "Alert Settings",
    descriptionKey: "help.pages.alertsettings",
    descriptionDefault: "Configure the thresholds that trigger portfolio alerts.",
  },
];

export default function Help() {
  const { t } = useTranslation();

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
          {HELP_PAGES.map((entry) => (
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
