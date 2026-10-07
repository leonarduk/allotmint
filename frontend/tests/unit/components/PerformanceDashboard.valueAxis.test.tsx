import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "@/i18n";
import { PerformanceDashboard } from "@/components/PerformanceDashboard";
import {
  getPerformance,
  getAlphaVsBenchmark,
  getTrackingError,
  getMaxDrawdown,
  getFxAttribution,
} from "@/api";

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

type AxisProps = {
  domain?: unknown;
  tickFormatter?: (v: number) => string;
};

// jsdom has no layout, so recharts' ResponsiveContainer renders nothing.
// Swap the chart primitives for prop-capturing stand-ins so the test can
// assert what /performance actually hands the Portfolio Value y-axis.
const yAxisProps = vi.hoisted(() => [] as AxisProps[]);
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Passthrough,
    LineChart: Passthrough,
    Line: () => null,
    XAxis: () => null,
    Tooltip: () => null,
    ReferenceArea: () => null,
    YAxis: (props: AxisProps) => {
      yAxisProps.push(props);
      return null;
    },
  };
});

describe("PerformanceDashboard Portfolio Value axis (#7815)", () => {
  beforeEach(() => {
    yAxisProps.length = 0;
    i18n.changeLanguage("en");
    vi.mocked(getFxAttribution).mockResolvedValue({ owner: "jane", fx_attribution: null });
    vi.mocked(getAlphaVsBenchmark).mockResolvedValue({ alpha_vs_benchmark: 0.01 });
    vi.mocked(getTrackingError).mockResolvedValue({ tracking_error: 0.02 });
    vi.mocked(getMaxDrawdown).mockResolvedValue({
      max_drawdown: -0.05,
      peak: { date: "2024-01-01", value: 72000 },
      trough: { date: "2024-06-01", value: 68400, drawdown: -0.05 },
      series: [],
    });
    vi.mocked(getPerformance).mockResolvedValue({
      history: [
        { date: "2024-01-01", value: 66000, cumulative_return: 0 },
        { date: "2024-06-01", value: 69000, cumulative_return: 0.045 },
        { date: "2024-12-31", value: 72000, cumulative_return: 0.09 },
      ],
      time_weighted_return: 0.09,
      xirr: 0.09,
      reportingDate: "2024-12-31",
      previousDate: "2024-12-30",
    });
  });

  it("fits the y-axis to the series, not 0, with currency ticks", async () => {
    render(
      <MemoryRouter>
        <PerformanceDashboard owner="jane" />
      </MemoryRouter>,
    );
    await screen.findByTestId("reporting-date-summary");

    const valueAxis = yAxisProps
      .filter((p) => Array.isArray(p.domain) && typeof (p.domain as unknown[])[0] === "number")
      .at(-1);
    expect(valueAxis).toBeDefined();
    const [lower, upper] = valueAxis!.domain as [number, number];
    expect(lower).toBeGreaterThan(0);
    expect(lower).toBeLessThan(66000);
    expect(upper).toBeGreaterThan(72000);
    expect(valueAxis!.tickFormatter!(70000)).toMatch(/£70,000/);
  });
});
