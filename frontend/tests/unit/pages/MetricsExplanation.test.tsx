import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { axe } from "jest-axe";
import MetricsExplanation from "@/pages/MetricsExplanation";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/metrics-explained"]}>
      <MetricsExplanation />
    </MemoryRouter>,
  );
}

describe("MetricsExplanation", () => {
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
