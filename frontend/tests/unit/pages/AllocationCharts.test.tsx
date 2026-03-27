import type { ReactNode } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import AllocationCharts from "@/pages/AllocationCharts";
import { allocationChartRuntime } from "@/pages/AllocationCharts";
import * as api from "@/api";
import type { GroupPortfolio, Holding } from "@/types";

vi.mock("@/api");
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  PieChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: ({ data, children }: { data: Array<{ name: string; value: number }>; children: ReactNode }) => (
    <div data-testid="pie-slices">
      {data.length === 0 ? (
        <span data-testid="no-slices">no-slices</span>
      ) : (
        data.map((slice) => (
          <span key={slice.name} data-testid="slice-row">{`${slice.name}: ${slice.value}`}</span>
        ))
      )}
      {children}
    </div>
  ),
  Cell: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));

const mockGetGroupPortfolio = vi.mocked(api.getGroupPortfolio);

const baseHolding: Holding = {
  ticker: "AAA",
  name: "Alpha",
  units: 1,
  acquired_date: "2024-01-01",
  market_value_gbp: 100,
  instrument_type: "equity",
  sector: "Tech",
  region: "UK",
};

const samplePortfolio: GroupPortfolio = {
  slug: "g",
  name: "Group",
  as_of: "2024-01-01",
  members: [],
  total_value_estimate_gbp: 100,
  trades_this_month: 0,
  trades_remaining: 0,
  accounts: [
    {
      account_type: "taxable",
      currency: "GBP",
      value_estimate_gbp: 100,
      owner: "alice",
      holdings: [baseHolding],
    },
  ],
  members_summary: [],
  subtotals_by_account_type: {},
};

const buildPortfolio = (holdings: Holding[]): GroupPortfolio => ({
  ...samplePortfolio,
  accounts: [{ ...samplePortfolio.accounts[0], holdings }],
});

describe("AllocationCharts page", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    allocationChartRuntime.isDev = true;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("shows loading indicator while fetching", async () => {
    let resolveFn: (p: GroupPortfolio) => void;
    const promise = new Promise<GroupPortfolio>((resolve) => {
      resolveFn = resolve;
    });
    mockGetGroupPortfolio.mockReturnValueOnce(promise);

    render(<AllocationCharts />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();

    resolveFn!(samplePortfolio);
    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });

  it("displays an error message when API call fails", async () => {
    mockGetGroupPortfolio.mockRejectedValueOnce(new Error("boom"));
    render(<AllocationCharts />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });

  it("keeps valid values across type/sector/region while excluding invalid entries", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NEG", market_value_gbp: -20, sector: "Utilities", region: "EU" },
        { ...baseHolding, ticker: "BAD", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "OK", market_value_gbp: 100, sector: "Tech", region: "UK" },
      ]),
    );

    render(<AllocationCharts />);

    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    // asset/type dimension
    let slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Equity: 100")).toBeInTheDocument();

    // sector dimension
    fireEvent.click(screen.getByRole("button", { name: /industries|sector/i }));
    slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 100")).toBeInTheDocument();
    expect(within(slices).queryByText(/Utilities/)).not.toBeInTheDocument();
    expect(within(slices).queryByText(/Finance/)).not.toBeInTheDocument();

    // region dimension
    fireEvent.click(screen.getByRole("button", { name: /regions|region/i }));
    slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("UK: 100")).toBeInTheDocument();
    expect(within(slices).queryByText(/^EU:/)).not.toBeInTheDocument();

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "NEG",
      originalValue: -20,
      coercedValue: -20,
      originalInvalid: false,
    });
  });

  it("excludes zero market values", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "ZERO", market_value_gbp: 0, sector: "Zero Sector" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 50, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /industries|sector/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 50")).toBeInTheDocument();
    expect(within(slices).queryByText(/Zero Sector/)).not.toBeInTheDocument();
  });

  it("excludes infinity and negative infinity values", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Energy" },
        { ...baseHolding, ticker: "NINF", market_value_gbp: Number.NEGATIVE_INFINITY, sector: "Materials" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 25, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /industries|sector/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 25")).toBeInTheDocument();
    expect(within(slices).queryByText(/Energy/)).not.toBeInTheDocument();
    expect(within(slices).queryByText(/Materials/)).not.toBeInTheDocument();
  });

  it("warns in dev for dropped NaN values and reports original value", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 10, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "NAN",
      originalValue: Number.NaN,
      coercedValue: 0,
      originalInvalid: true,
    });
  });

  it("warns in dev for dropped Infinity values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Energy" },
        { ...baseHolding, ticker: "VALID", market_value_gbp: 10, sector: "Tech" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "INF",
      originalValue: Number.POSITIVE_INFINITY,
      coercedValue: 0,
      originalInvalid: true,
    });
  });

  it("warns in dev for dropped non-numeric values", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        {
          ...baseHolding,
          ticker: "STR",
          // Runtime API payloads can still return non-numeric data despite frontend type declarations.
          market_value_gbp: "N/A" as unknown as number,
          sector: "Unknown",
        },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    expect(warnSpy).toHaveBeenCalledWith("Dropped invalid holding value", {
      ticker: "STR",
      originalValue: "N/A",
      coercedValue: 0,
      originalInvalid: true,
    });
  });

  it("renders an empty chart state when all holdings are invalid", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Finance" },
        { ...baseHolding, ticker: "NEG", market_value_gbp: -10, sector: "Utilities" },
        { ...baseHolding, ticker: "ZERO", market_value_gbp: 0, sector: "Zero" },
      ]),
    );

    render(<AllocationCharts />);

    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
    expect(screen.getByTestId("no-slices")).toBeInTheDocument();
  });

  it("preserves aggregation sums for multiple valid holdings", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "AAA", market_value_gbp: 30, sector: "Tech" },
        { ...baseHolding, ticker: "BBB", market_value_gbp: 70, sector: "Tech" },
        { ...baseHolding, ticker: "CCC", market_value_gbp: 50, sector: "Health" },
      ]),
    );

    render(<AllocationCharts />);

    await screen.findByText(/Instrument Types/);
    fireEvent.click(screen.getByRole("button", { name: /industries|sector/i }));

    const slices = screen.getByTestId("pie-slices");
    expect(within(slices).getByText("Tech: 100")).toBeInTheDocument();
    expect(within(slices).getByText("Health: 50")).toBeInTheDocument();
  });

  it("suppresses all dropped-value warnings in production", async () => {
    allocationChartRuntime.isDev = false;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    mockGetGroupPortfolio.mockResolvedValueOnce(
      buildPortfolio([
        { ...baseHolding, ticker: "NEG", market_value_gbp: -1, sector: "Utilities" },
        { ...baseHolding, ticker: "NAN", market_value_gbp: Number.NaN as unknown as number, sector: "Utilities" },
        { ...baseHolding, ticker: "INF", market_value_gbp: Number.POSITIVE_INFINITY, sector: "Utilities" },
        { ...baseHolding, ticker: "STR", market_value_gbp: "N/A" as unknown as number, sector: "Utilities" },
      ]),
    );

    render(<AllocationCharts />);
    await screen.findByText(/Instrument Types/);

    expect(warnSpy).not.toHaveBeenCalled();
  });
});
