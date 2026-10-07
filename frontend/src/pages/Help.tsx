import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SectionCard from "../components/SectionCard";
import { useConfig } from "../ConfigContext";
import { visibleHelpPages } from "../lib/helpPages";

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

export default function Help() {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const visiblePages = visibleHelpPages(tabs, disabledTabs);

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
