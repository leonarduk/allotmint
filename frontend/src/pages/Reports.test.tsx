import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { configContext } from "../ConfigContext";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetGroups = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  API_BASE: "http://test",
  getOwners: mockGetOwners,
  getGroups: mockGetGroups,
  getGroupInstruments: vi.fn().mockResolvedValue([]),
  getPortfolio: vi.fn(),
  refreshPrices: vi.fn(),
  getAlerts: vi.fn().mockResolvedValue([]),
  getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
  getCompliance: vi
    .fn()
    .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
  getTimeseries: vi.fn().mockResolvedValue([]),
  saveTimeseries: vi.fn(),
  refetchTimeseries: vi.fn(),
  rebuildTimeseriesCache: vi.fn(),
  getTradingSignals: vi.fn().mockResolvedValue([]),
  getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
  listTimeseries: vi.fn().mockResolvedValue([]),
}));

const allTabs = {
  group: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: true,
  trading: true,
  screener: true,
  timeseries: true,
  watchlist: true,
  allocation: true,
  market: true,
  rebalance: true,
  movers: true,
  instrumentadmin: true,
  dataadmin: true,
  virtual: true,
  support: true,
  settings: true,
  pension: true,
  reports: true,
  scenario: true,
  logs: true,
};

describe("Reports page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders links when owner selected", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetGroups.mockResolvedValue([]);

    window.history.pushState({}, "", "/reports");
    const { default: Reports } = await import("./Reports");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          disabledTabs: [],
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/reports"]}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>
    );

    const select = await screen.findByLabelText(/owner/i);
    fireEvent.change(select, { target: { value: "alex" } });

    const csv = await screen.findByText(/Download CSV/i);
    expect(csv).toHaveAttribute(
      "href",
      expect.stringContaining("/reports/alex")
    );
  });

  it("shows message when no owners", async () => {
    mockGetOwners.mockResolvedValue([]);
    mockGetGroups.mockResolvedValue([]);

    window.history.pushState({}, "", "/reports");
    const { default: Reports } = await import("./Reports");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          disabledTabs: [],
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/reports"]}>
          <Reports />
        </MemoryRouter>
      </configContext.Provider>
    );

    const message = await screen.findByText(
      /No owners available—check backend connection/i
    );
    expect(message).toBeInTheDocument();
    expect(screen.queryByLabelText(/owner/i)).not.toBeInTheDocument();
  });
});

