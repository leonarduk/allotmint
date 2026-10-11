import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";
import MetricsExplanation from "@/pages/MetricsExplanation";
import { TECHNICALS_GLOSSARY } from "@/lib/technicalsGlossary";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/metrics-explained"]}>
      <MetricsExplanation />
    </MemoryRouter>,
  );
}

describe("MetricsExplanation", () => {
  it("has an entry for every technicals term the research page links to", () => {
    const { container } = renderPage();

    expect(container.querySelector("#technical-analysis")).not.toBeNull();
    for (const entry of TECHNICALS_GLOSSARY) {
      const node = container.querySelector(`#${entry.id}`);
      expect(node).not.toBeNull();
      expect(node?.textContent).toContain(entry.detail);
    }
    expect(screen.getByText("Golden cross and death cross")).toBeInTheDocument();
  });

  it("scrolls to the entry named in the URL fragment", () => {
    const scrolled: string[] = [];
    // jsdom does not implement scrollIntoView, so stub it for this test only.
    const original = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = vi.fn(function (this: HTMLElement) {
      scrolled.push(this.id);
    });
    try {
      render(
        <MemoryRouter initialEntries={["/metrics-explained#golden-death-cross"]}>
          <MetricsExplanation />
        </MemoryRouter>,
      );
      expect(scrolled).toEqual(["golden-death-cross"]);
    } finally {
      HTMLElement.prototype.scrollIntoView = original;
    }
  });

  it("covers the jargon terms used elsewhere in the app with a stable anchor each", () => {
    const { container } = renderPage();

    const anchors = [
      "alpha-vs-benchmark",
      "tracking-error",
      "max-drawdown",
      "time-weighted-return",
      "xirr",
      "rsi",
      "moving-average",
      "sharpe-ratio",
      "screener-risk-return",
      "debt-equity",
      "volatility",
      "checks-skipped",
      "peg-ratio",
      "lt-debt-equity",
      "interest-coverage",
      "current-ratio",
      "quick-ratio",
      "free-cash-flow",
      "eps",
      "roa",
      "roe",
      "roi",
      "beta",
      "market-cap",
      "buy-sell-signal",
      "beds",
      "propagator",
      "water",
      "feed",
      "sunlight",
      "sown",
      "budding",
      "leafing",
      "fruiting",
    ];

    for (const anchor of anchors) {
      expect(container.querySelector(`#${anchor}`)).not.toBeNull();
    }
  });

  it("explains growth stages by gain percentage, not holding period", () => {
    renderPage();

    expect(
      screen.getByText(/total gain of -20% or below/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not depend on how long it has been held/i),
    ).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderPage();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
