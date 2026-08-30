import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import i18n from "@/i18n";
import Help from "@/pages/Help";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

describe("Help page", () => {
  it("explains what the main pages do, links the metrics glossary, and links how to report a problem", () => {
    render(<Help />, { wrapper: MemoryRouter });

    expect(
      screen.getByRole("heading", { name: i18n.t("help.title", "Help & Getting Started") }),
    ).toBeInTheDocument();

    // A page description with a link back to that page (#7226). Its own
    // dedicated title ("Dashboard"), not app.modes.group ("Group") -- that
    // key already resolves to different text elsewhere in the app.
    const dashboardLink = screen.getByRole("link", {
      name: i18n.t("help.pages.dashboardTitle", "Dashboard"),
    });
    expect(dashboardLink).toHaveAttribute("href", "/");

    // Links the metrics glossary rather than rebuilding it (#7230 makes it
    // reachable elsewhere; this page just points at it).
    const glossaryLink = screen.getByRole("link", {
      name: i18n.t("help.glossaryLink", "Open the metrics glossary"),
    });
    expect(glossaryLink).toHaveAttribute("href", "/metrics-explained");

    // A way to report a problem.
    const reportLink = screen.getByRole("link", {
      name: i18n.t("help.reportLink", "Open a GitHub issue"),
    });
    expect(reportLink).toHaveAttribute(
      "href",
      "https://github.com/leonarduk/allotmint/issues/new",
    );
  });

  it("does not link a page whose tab is disabled (#7226)", () => {
    // Mirrors this repo's own config.yaml (transactions/reports/taxtools:
    // false) -- a Help page with dead links is worse than no Help page at
    // all, per the issue.
    const config: ConfigContextValue = {
      relativeViewEnabled: false,
      disabledTabs: ["transactions", "reports", "taxtools"],
      tabs: {
        group: true,
        market: true,
        movers: true,
        instrument: true,
        performance: true,
        transactions: false,
        trading: true,
        screener: true,
        watchlist: true,
        allocation: true,
        rebalance: true,
        reports: false,
        pension: true,
        taxtools: false,
        research: true,
        settings: true,
        alertsettings: true,
      },
      theme: "system",
      baseCurrency: "GBP",
      refreshConfig: async () => {},
      setRelativeViewEnabled: () => {},
      setBaseCurrency: () => {},
    };
    render(
      <configContext.Provider value={config}>
        <Help />
      </configContext.Provider>,
      { wrapper: MemoryRouter },
    );

    expect(
      screen.queryByRole("link", { name: i18n.t("app.modes.transactions") }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: i18n.t("app.modes.reports") }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: i18n.t("app.modes.taxtools") }),
    ).not.toBeInTheDocument();

    // A still-enabled page keeps its link.
    expect(
      screen.getByRole("link", { name: i18n.t("app.modes.market") }),
    ).toBeInTheDocument();
  });
});
