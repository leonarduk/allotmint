import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import * as api from "@/api";
import MarketOverview from "@/pages/MarketOverview";

vi.mock("@/api");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, opts?: any) => opts?.defaultValue ?? _k }),
}));

var mockBar: any;

vi.mock("recharts", () => {
  mockBar = vi.fn(() => null);
  return {
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
  };
});

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
});
