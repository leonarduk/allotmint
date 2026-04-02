import { render, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const baseConfig = {
  relativeViewEnabled: false,
  disabledTabs: ["owner", "performance", "transactions"],
  tabs: {
    group: true,
    market: true,
    owner: false,
    instrument: true,
    performance: false,
    transactions: false,
    screener: true,
    trading: true,
    timeseries: true,
    watchlist: true,
    allocation: true,
    rebalance: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    research: true,
    support: true,
    settings: true,
    profile: false,
    alerts: true,
    pension: true,
    trail: false,
    alertsettings: true,
    taxtools: false,
    "trade-compliance": false,
    reports: false,
    scenario: true,
  },
  theme: "system",
  baseCurrency: "GBP",
  enableAdvancedAnalytics: true,
  refreshConfig: vi.fn(),
  setRelativeViewEnabled: vi.fn(),
  setBaseCurrency: vi.fn(),
};

describe("App family MVP redirects", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("does not redirect root routes before config finishes loading", async () => {
    window.history.pushState({}, "", "/");

    vi.doMock("@/ConfigContext", async () => {
      const actual = await vi.importActual<typeof import("@/ConfigContext")>("@/ConfigContext");
      return {
        ...actual,
        useConfig: () => ({
          ...baseConfig,
          configLoaded: false,
        }),
      };
    });

    vi.doMock("@/api", async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
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
      };
    });

    const App = (await import("@/App")).default;
    const router = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/"] },
    );

    render(<RouterProvider router={router} />);

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
