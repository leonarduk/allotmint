import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
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
  LineChart: ({ children }: any) => <div>{children}</div>,
  Line: () => null,
  XAxis: mockXAxis,
  YAxis: () => null,
  Tooltip: () => null,
  Cell: mockCell,
}));

const mockGetMarketOverview = vi.mocked(api.getMarketOverview);
const mockGetMarketSectors = vi.mocked(api.getMarketSectors);
const mockGetSectorDetail = vi.mocked(api.getSectorDetail);

const emptyOverview = { indexes: {}, sectors: [], headlines: [] };

beforeEach(() => {
  mockBar.mockClear();
  mockGetMarketOverview.mockClear();
  mockGetMarketSectors.mockReset();
  mockGetSectorDetail.mockReset();
  mockGetMarketSectors.mockResolvedValue({ region: "us", sectors: [] });
});

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
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "us",
      sectors: [
        { sector: "Energy", change: 1.1, source: "etf" },
        { sector: "Real Estate", change: -0.1, source: "etf" },
        { sector: "Utilities", change: 0, source: "etf" },
      ],
    });
    render(<MarketOverview />);
    expect(
      await screen.findByRole("heading", { name: "Sector % Change" }),
    ).toBeInTheDocument();
    await screen.findByRole("button", { name: /Real Estate/ });
    const sectorFills = mockCell.mock.calls
      .map(([props]: any) => props)
      .filter((props: any) => "strokeWidth" in props)
      .map((props: any) => props.fill);
    expect(sectorFills).toEqual(["#16a34a", "#dc2626", "#16a34a"]);
    expect(screen.queryByText(/equal-weighted baskets/)).not.toBeInTheDocument();
  });

  it("discloses when sector moves are constituent baskets", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "uk",
      sectors: [{ sector: "Energy", change: 0.5, source: "basket" }],
    });
    render(<MarketOverview />);
    expect(await screen.findByText(/equal-weighted baskets/)).toBeInTheDocument();
  });

  it("labels the sector value axis with % units (#7817)", async () => {
    mockXAxis.mockClear();
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "us",
      sectors: [{ sector: "Energy", change: 1.234, source: "etf" }],
    });
    render(<MarketOverview />);
    await screen.findByRole("button", { name: /Energy/ });
    const valueAxis = mockXAxis.mock.calls
      .map(([props]: any) => props)
      .find((props: any) => props.type === "number");
    expect(valueAxis).toBeDefined();
    expect(valueAxis.tickFormatter(1.234)).toBe("1.2%");
    expect(valueAxis.label.value).toBe("% Change");
  });

  it("shows an empty state instead of a blank chart when there are no sectors", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    render(<MarketOverview />);
    expect(await screen.findByText("No sector data available")).toBeInTheDocument();
  });
});

describe("MarketOverview sectors (#9381)", () => {
  it("asks the overview to skip sectors and loads the default region", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "uk",
      sectors: [{ sector: "Energy", change: 1.5, source: "basket" }],
    });
    render(<MarketOverview />);

    expect(await screen.findByRole("button", { name: /Energy/ })).toBeInTheDocument();
    expect(mockGetMarketOverview).toHaveBeenLastCalledWith({ includeSectors: false });
    expect(mockGetMarketSectors).toHaveBeenCalledWith(undefined, expect.any(AbortSignal));
    const toggle = screen.getByRole("group", { name: "Sector region" });
    expect(within(toggle).getByRole("button", { name: "UK" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("refetches sectors when a different region is chosen", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    render(<MarketOverview />);
    const toggle = await screen.findByRole("group", { name: "Sector region" });

    fireEvent.click(within(toggle).getByRole("button", { name: "Global" }));

    await waitFor(() =>
      expect(mockGetMarketSectors).toHaveBeenLastCalledWith("global", expect.any(AbortSignal)),
    );
    expect(mockGetMarketOverview).toHaveBeenCalledTimes(1);
  });

  it("opens sector detail when a sector is clicked", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "us",
      sectors: [{ sector: "Energy", change: -0.4, source: "etf" }],
    });
    mockGetSectorDetail.mockResolvedValueOnce({
      region: "us",
      sector: "Energy",
      basis: "etf",
      proxy: { ticker: "XLE", name: "Energy Select Sector SPDR" },
      returns: { "1D": -0.4, "1W": 1.2, "1M": null, YTD: 5 },
      history: [{ date: "2026-10-02", value: 90 }],
      constituents: [{ ticker: "XOM", name: "Exxon Mobil", price: 110.5, change: -0.8 }],
    });
    render(<MarketOverview />);

    fireEvent.click(await screen.findByRole("button", { name: /Energy/ }));

    const panel = await screen.findByRole("region", { name: "Sector detail" });
    expect(mockGetSectorDetail).toHaveBeenCalledWith("us", "Energy", expect.any(AbortSignal));
    expect(await within(panel).findByText("Exxon Mobil")).toBeInTheDocument();
    expect(within(panel).getByText(/Tracked via/)).toBeInTheDocument();
    expect(within(panel).getByText("1.20%")).toBeInTheDocument();
    expect(within(panel).getByText("—")).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Sector detail" })).not.toBeInTheDocument();
  });

  it("wires bar clicks to the same selection", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "us",
      sectors: [{ sector: "Utilities", change: 0.2, source: "etf" }],
    });
    mockGetSectorDetail.mockReturnValueOnce(new Promise(() => {}));
    render(<MarketOverview />);
    await screen.findByRole("button", { name: /Utilities/ });

    const sectorBar = mockBar.mock.calls
      .map((call: any[]) => call[0])
      .find((props: any) => typeof props.onClick === "function");
    sectorBar.onClick({}, 0);

    await waitFor(() =>
      expect(mockGetSectorDetail).toHaveBeenCalledWith("us", "Utilities", expect.any(AbortSignal)),
    );
  });

  it("shows the backend error when sector detail fails", async () => {
    mockGetMarketOverview.mockResolvedValueOnce(emptyOverview);
    mockGetMarketSectors.mockResolvedValueOnce({
      region: "uk",
      sectors: [{ sector: "Energy", change: 0.1, source: "basket" }],
    });
    mockGetSectorDetail.mockRejectedValueOnce(new Error("Sector data is unavailable"));
    render(<MarketOverview />);

    fireEvent.click(await screen.findByRole("button", { name: /Energy/ }));

    expect(await screen.findByText("Sector data is unavailable")).toBeInTheDocument();
  });
});
