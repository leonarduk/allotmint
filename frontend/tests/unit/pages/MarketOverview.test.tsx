import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import * as api from "@/api";
import MarketOverview, { IndexTooltip } from "@/pages/MarketOverview";

vi.mock("@/api");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, opts?: any) => opts?.defaultValue ?? _k }),
}));

// vi.hoisted ensures mockBar is initialised before vi.mock factories run.
const mockBar = vi.hoisted(() => vi.fn(() => null));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ data, children }: any) => (
    <div>
      {data.map((d: any) => (
        <div key={d.name}>{d.name}</div>
      ))}
      {children}
    </div>
  ),
  Bar: mockBar,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Cell: () => null,
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
    expect(mockBar.mock.calls[0][0].dataKey).toBe("value");
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
});
