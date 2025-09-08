import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import * as api from "../api";
import MarketOverview from "./MarketOverview";

vi.mock("../api");
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_k: string, opts?: any) => opts?.defaultValue ?? _k }),
}));
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
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));

const mockGetMarketOverview = vi.mocked(api.getMarketOverview);

describe("MarketOverview", () => {
  it("renders UK index entries", async () => {
    mockGetMarketOverview.mockResolvedValueOnce({
      indexes: { "S&P 500": 100, "FTSE 100": 200, "FTSE 250": 300 },
      sectors: [],
      headlines: [],
    });
    render(<MarketOverview />);
    expect(await screen.findByText("FTSE 100")).toBeInTheDocument();
    expect(screen.getByText("FTSE 250")).toBeInTheDocument();
  });
});
