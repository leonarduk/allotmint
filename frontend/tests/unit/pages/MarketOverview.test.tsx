import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import * as api from "@/api";
import MarketOverview, { IndexTooltip } from "@/pages/MarketOverview";

vi.mock("@/api");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, opts?: any) => opts?.defaultValue ?? _k }),
}));

// vi.hoisted ensures mocks are initialised before vi.mock factories run.
const mockBar = vi.hoisted(() => vi.fn(({ children }: any) => <>{children}</>));
const mockCell = vi.hoisted(() => vi.fn(() => null));
const mockXAxis = vi.hoisted(() => vi.fn(() => null));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ data, children }: any) => (
    <div>
      {data.map((d: any) => (
        <div key={d.name ?? d.sector}>{d.name}</div>
      ))}
      {children}
    </div>
  ),
  Bar: mockBar,
  XAxis: mockXAxis,
  YAxis: () => null,
  Tooltip: () => null,
  Cell: mockCell,
}));

const mockGetMarketOverview = vi.mocked(api.getMarketOverview);

describe("MarketOverview", () => {
  it("renders UK index entries and shows empty headline message", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {
        "S&P 500": { value: 100, change: 0 },
        "FTSE 100": { value: 200, change: 0 },
        "FTSE 250": { value: 300, change: 0 },
      },
      sectors: [],
      headlines: [],
    });
    render(<MarketOverview />);
    const ftse = await screen.findAllByText("FTSE 100");
    expect(ftse.length).toBeGreaterThan(0);
    expect(screen.getAllByText("FTSE 250")).toHaveLength(2);
    expect(screen.getByText("No headlines available")).toBeInTheDocument();
    expect(mockBar).toHaveBeenCalled();
    expect(mockBar.mock.calls[0][0].dataKey).toBe("change");
    // The bars plot % change, so the heading must not say "Index Levels"
    // (that mislabel was #2541).
    expect(
      screen.getByRole("heading", { name: "Index % Change" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Index Levels")).not.toBeInTheDocument();
  });

  it("renders headlines when provided", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [{ headline: "Some News", url: "https://example.com" }],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("Some News")).toBeInTheDocument();
  });

  it("renders the published age next to a dated headline", async () => {
    const published = new Date(Date.now() - 3 * 86400 * 1000).toISOString();
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [
        {
          headline: "Dated News",
          url: "https://example.com/dated",
          published_at: published,
        },
      ],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("Dated News")).toBeInTheDocument();
    expect(screen.getByText(/3 days ago/)).toBeInTheDocument();
  });

  it("omits the age when a headline has no published date", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [{ headline: "Undated News", url: "https://example.com/undated" }],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("Undated News")).toBeInTheDocument();
    expect(screen.queryByText(/ago/)).not.toBeInTheDocument();
  });

  it("shows a stale badge for a headline flagged as stale", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [
        { headline: "Old News", url: "https://example.com/old", stale: true },
      ],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("Old News")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("omits the stale badge for a fresh headline", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [
        { headline: "Fresh News", url: "https://example.com/fresh", stale: false },
      ],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("Fresh News")).toBeInTheDocument();
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  });

  it("renders index tooltip values from value and change", () => {
    render(
      <IndexTooltip
        active
        label="S&P 500"
        payload={[{ payload: { value: 6123.45, change: -0.22 } }]}
      />
    );

    expect(screen.getByText("Level: 6,123.45")).toBeInTheDocument();
    expect(screen.getByText("Change: -0.22%")).toBeInTheDocument();
  });

  it("colours sector bars by sign and labels the axis as % change (#7817)", async () => {
    mockCell.mockClear();
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [
        { sector: "Energy", change: 1.1, source: "lse" },
        { sector: "Real Estate", change: -0.1, source: "lse" },
        { sector: "Utilities", change: 0, source: "lse" },
      ],
      headlines: [],
    });
    render(<MarketOverview />);
    expect(
      await screen.findByRole("heading", { name: "Sector % Change" }),
    ).toBeInTheDocument();
    const sectorFills = mockCell.mock.calls.map(([props]: any) => props.fill);
    expect(sectorFills).toEqual(["#16a34a", "#dc2626", "#16a34a"]);
    expect(
      screen.queryByText(/showing US sector ETF performance/),
    ).not.toBeInTheDocument();
  });

  it("discloses when sector data comes from the US ETF fallback", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [{ sector: "Energy", change: 0.5, source: "us_etf" }],
      headlines: [],
    });
    render(<MarketOverview />);
    expect(
      await screen.findByText(/showing US sector ETF performance/),
    ).toBeInTheDocument();
  });

  it("labels the sector value axis with % units (#7817)", async () => {
    mockXAxis.mockClear();
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [{ sector: "Energy", change: 1.234, source: "lse" }],
      headlines: [],
    });
    render(<MarketOverview />);
    await screen.findByRole("heading", { name: "Sector % Change" });
    const valueAxis = mockXAxis.mock.calls
      .map(([props]: any) => props)
      .find((props: any) => props.type === "number");
    expect(valueAxis).toBeDefined();
    expect(valueAxis.tickFormatter(1.234)).toBe("1.2%");
    expect(valueAxis.label.value).toBe("% Change");
  });

  it("shows an empty state instead of a blank chart when there are no sectors", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: {},
      sectors: [],
      headlines: [],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("No sector data available")).toBeInTheDocument();
  });
});
