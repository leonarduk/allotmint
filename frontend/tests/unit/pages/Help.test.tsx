import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import i18n from "@/i18n";
import Help from "@/pages/Help";

describe("Help page", () => {
  it("explains what the main pages do, links the metrics glossary, and links how to report a problem", () => {
    render(<Help />, { wrapper: MemoryRouter });

    expect(
      screen.getByRole("heading", { name: i18n.t("help.title", "Help & Getting Started") }),
    ).toBeInTheDocument();

    // A page description with a link back to that page (#7226).
    const dashboardLink = screen.getByRole("link", {
      name: i18n.t("app.modes.group"),
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
});
