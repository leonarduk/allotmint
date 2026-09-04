import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// PortfolioDashboard renders two recharts <LineChart>s. jsdom has no layout
// engine, so ResponsiveContainer never reports a size and recharts renders
// nothing inside it -- mock it the same way AllocationCharts/MarketOverview
// tests do, so the chart data itself is inspectable.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({
    data,
    children,
  }: {
    data: { date: string; value: number; cumulative_return: number }[];
    children: React.ReactNode;
  }) => (
    <div data-testid="line-chart" data-points={data.length}>
      {children}
    </div>
  ),
  Line: ({ dataKey }: { dataKey: string }) => (
    <div data-testid={`line-${dataKey}`} />
  ),
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));

import PortfolioDashboard from "@/pages/PortfolioDashboard";
import PortfolioDashboardSkeleton from "@/components/skeletons/PortfolioDashboardSkeleton";

const populatedProps = {
  twr: 0.1234,
  irr: 0.0567,
  bestDay: 0.021,
  worstDay: -0.015,
  lastDay: 0.003,
  alpha: 0.012,
  trackingError: 0.045,
  maxDrawdown: -0.089,
  volatility: 0.15,
  data: [
    { date: "2024-01-01", value: 1000, cumulative_return: 0 },
    { date: "2024-02-01", value: 1050, cumulative_return: 0.05 },
  ],
};

function renderDashboard(
  props: Partial<typeof populatedProps> & { owner?: string } = {},
) {
  return render(
    <MemoryRouter>
      <PortfolioDashboard {...populatedProps} {...props} />
    </MemoryRouter>,
  );
}

describe("PortfolioDashboard page", () => {
  // PortfolioDashboard.tsx itself is a pure, props-driven presentational
  // component -- it has no internal fetch/loading/error state of its own
  // (that logic lives in its data-fetching parent, PerformanceDashboard.tsx,
  // which is out of scope for this file). So there is no "fetch-error
  // state" to exercise here: every prop this component receives is already
  // resolved data (or null) by the time it renders. The loading UI shown
  // while that data is being fetched is the sibling
  // PortfolioDashboardSkeleton component, rendered by the parent
  // (App.tsx's <Suspense fallback={<PortfolioDashboardSkeleton />}>) while
  // PerformanceDashboard resolves. That skeleton has no test coverage
  // anywhere else in the suite, so it is verified here as this page's
  // loading state.
  describe("loading state", () => {
    it("shows the KPI and chart skeleton placeholders", () => {
      const { container } = render(<PortfolioDashboardSkeleton />);

      // KPISkeleton renders 5 pulsing tiles; the two ChartSkeleton instances
      // (one per chart PortfolioDashboard eventually shows) contribute one
      // pulsing placeholder each -- 7 pulsing elements total.
      expect(container.querySelectorAll(".animate-pulse").length).toBe(7);
    });

    it("announces the loading state to screen readers when given a label", () => {
      render(<PortfolioDashboardSkeleton label="Loading dashboard" />);

      const status = screen.getByRole("status", { name: "Loading dashboard" });
      expect(status).toBeInTheDocument();
    });
  });

  describe("populated state", () => {
    it("renders KPI metrics as formatted percentages", () => {
      renderDashboard();

      expect(screen.getByText("TWR")).toBeInTheDocument();
      expect(screen.getByText("12.34%")).toBeInTheDocument();
      expect(screen.getByText("IRR")).toBeInTheDocument();
      expect(screen.getByText("5.67%")).toBeInTheDocument();
      expect(screen.getByText("Best Day")).toBeInTheDocument();
      expect(screen.getByText("2.10%")).toBeInTheDocument();
      expect(screen.getByText("Worst Day")).toBeInTheDocument();
      expect(screen.getByText("-1.50%")).toBeInTheDocument();
      expect(screen.getByText("Last Day")).toBeInTheDocument();
      expect(screen.getByText("0.30%")).toBeInTheDocument();
    });

    it("renders benchmark-relative metrics", () => {
      renderDashboard();

      expect(screen.getByText("Alpha vs Benchmark")).toBeInTheDocument();
      expect(screen.getByText("1.20%")).toBeInTheDocument();
      expect(screen.getByText("Tracking Error")).toBeInTheDocument();
      expect(screen.getByText("4.50%")).toBeInTheDocument();
      expect(screen.getByText("Max Drawdown")).toBeInTheDocument();
      expect(screen.getByText("-8.90%")).toBeInTheDocument();
      expect(screen.getByText("Volatility")).toBeInTheDocument();
      expect(screen.getByText("15.00%")).toBeInTheDocument();
    });

    it("renders the value and cumulative-return charts with the supplied series", () => {
      renderDashboard();

      expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
      expect(screen.getByText("Cumulative Return")).toBeInTheDocument();
      const charts = screen.getAllByTestId("line-chart");
      expect(charts).toHaveLength(2);
      charts.forEach((chart) => expect(chart.dataset.points).toBe("2"));
      expect(screen.getByTestId("line-value")).toBeInTheDocument();
      expect(screen.getByTestId("line-cumulative_return")).toBeInTheDocument();
    });

    it("links to the return comparison page for the given owner", () => {
      renderDashboard({ owner: "alex" });

      const link = screen.getByRole("link", { name: "Return Comparison" });
      expect(link).toHaveAttribute("href", "/returns/compare?owner=alex");
    });

    it("links to return comparison without an owner query when no owner is set", () => {
      renderDashboard({ owner: undefined });

      const link = screen.getByRole("link", { name: "Return Comparison" });
      expect(link).toHaveAttribute("href", "/returns/compare");
    });
  });

  describe("empty-portfolio state", () => {
    it("shows placeholder values and an empty chart when there is no data yet", () => {
      renderDashboard({
        twr: null,
        irr: null,
        bestDay: null,
        worstDay: null,
        lastDay: null,
        alpha: null,
        trackingError: null,
        maxDrawdown: null,
        volatility: null,
        data: [],
      });

      // percent() falls back to an em-dash for TWR/IRR/day metrics.
      expect(screen.getAllByText("—").length).toBe(5);
      // percentOrNa() falls back to "N/A" for the benchmark-relative metrics.
      expect(screen.getAllByText("N/A").length).toBe(4);

      const charts = screen.getAllByTestId("line-chart");
      expect(charts).toHaveLength(2);
      charts.forEach((chart) => expect(chart.dataset.points).toBe("0"));
    });
  });
});
