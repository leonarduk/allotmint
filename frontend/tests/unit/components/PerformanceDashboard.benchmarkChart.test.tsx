import { cloneElement, isValidElement } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/api", () => ({
  getPerformance: vi.fn(),
  getAlphaVsBenchmark: vi.fn(),
  getTrackingError: vi.fn(),
  getMaxDrawdown: vi.fn(),
  getGroupPerformance: vi.fn(),
  getGroupAlphaVsBenchmark: vi.fn(),
  getGroupTrackingError: vi.fn(),
  getGroupMaxDrawdown: vi.fn(),
  getFxAttribution: vi.fn(),
}));

// ResponsiveContainer measures its parent, which is always 0x0 in jsdom, so
// recharts renders nothing at all. Giving the chart an explicit size lets
// these tests assert on the lines and legend that actually reach the SVG.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      isValidElement(children)
        ? cloneElement(children as React.ReactElement<Record<string, unknown>>, {
            width: 800,
            height: 240,
          })
        : children,
  };
});

import i18n from "@/i18n";
import { PerformanceDashboard } from "@/components/PerformanceDashboard";
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
  getFxAttribution,
} from "@/api";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const point = (date: string, portfolio: number, benchmark: number) => ({
  date,
  portfolio_cumulative_return: portfolio,
  benchmark_cumulative_return: benchmark,
  excess_cumulative_return: portfolio - benchmark,
});

const renderDashboard = () =>
  render(
    <MemoryRouter>
      <PerformanceDashboard owner="jane" />
    </MemoryRouter>,
  );

describe("PerformanceDashboard Cumulative Return benchmark chart (#7833)", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", ResizeObserver);
    i18n.changeLanguage("en");
    vi.mocked(getFxAttribution).mockResolvedValue({ owner: "jane", fx_attribution: null });
    vi.mocked(getTrackingError).mockResolvedValue({ tracking_error: 0.02 });
    vi.mocked(getMaxDrawdown).mockResolvedValue({
      max_drawdown: -0.1,
      peak: null,
      trough: null,
      series: [],
    });
    vi.mocked(getPerformance).mockResolvedValue({
      history: [
        { date: "2024-03-01", value: 1000, cumulative_return: 0 },
        { date: "2024-03-28", value: 1100, cumulative_return: 0.1 },
      ],
      time_weighted_return: 0.04,
      xirr: 0.05,
      reportingDate: "2024-03-31",
      previousDate: "2024-02-29",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("draws portfolio and benchmark in distinct colours, both named in the legend", async () => {
    vi.mocked(getAlphaVsBenchmark).mockResolvedValue({
      alpha_vs_benchmark: 0.01,
      benchmark: "VWRL.L",
      series: [point("2024-03-01", 0, 0), point("2024-03-28", 0.05, 0.04)],
    });
    const { container } = renderDashboard();

    await screen.findByTestId("cumulative-return-basis");
    expect(screen.getByText("Your portfolio")).toBeInTheDocument();
    expect(screen.getByText("VWRL.L (benchmark)")).toBeInTheDocument();

    await waitFor(() => {
      const strokes = Array.from(
        container.querySelectorAll(".recharts-line-curve"),
      ).map((el) => el.getAttribute("stroke"));
      expect(strokes).toContain("#82ca9d");
      expect(strokes).toContain("#f59e0b");
    });
  });

  it("treats a series whose points are all non-finite as no benchmark", async () => {
    vi.mocked(getAlphaVsBenchmark).mockResolvedValue({
      alpha_vs_benchmark: null,
      benchmark: "VWRL.L",
      series: [
        point("2024-03-01", Number.NaN, 0),
        point("2024-03-28", 0.05, Number.POSITIVE_INFINITY),
      ],
    });
    renderDashboard();

    expect(
      await screen.findByTestId("benchmark-series-unavailable"),
    ).toHaveTextContent("No VWRL.L prices overlap this period");
    expect(screen.queryByTestId("cumulative-return-basis")).toBeNull();
    expect(screen.queryByText("VWRL.L (benchmark)")).toBeNull();
  });
});
