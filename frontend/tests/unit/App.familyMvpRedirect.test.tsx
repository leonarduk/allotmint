import { render, screen, waitFor } from "@testing-library/react";
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

async function mockCommonAppDependencies() {
  vi.doMock("@/api", async () => {
    const actual = await vi.importActual<typeof import("@/api")>("@/api");
    return {
      ...actual,
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi
        .fn()
        .mockResolvedValue([{ slug: "kids", name: "Kids", members: [] }]),
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
}

function mockConfig(overrides: Record<string, unknown>) {
  vi.doMock("@/ConfigContext", async () => {
    const actual = await vi.importActual<typeof import("@/ConfigContext")>("@/ConfigContext");
    return {
      ...actual,
      useConfig: () => ({
        ...baseConfig,
        ...overrides,
      }),
    };
  });
}

async function renderAppAt(path: string) {
  const App = (await import("@/App")).default;
  const router = createMemoryRouter(
    [{ path: "*", element: <App /> }],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("App family MVP redirects", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("does not redirect root routes before config finishes loading", async () => {
    window.history.pushState({}, "", "/");

    mockConfig({ configLoaded: false });

    await mockCommonAppDependencies();

    const router = await renderAppAt("/");

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("hides movers page content when family MVP is enabled and an entry route exists", async () => {
    mockConfig({
      configLoaded: true,
      familyMvpEnabled: true,
      disabledTabs: [],
      tabs: {
        ...baseConfig.tabs,
        owner: true,
      },
    });

    vi.doMock("@/pages/TopMovers", () => ({
      default: () => <h1>Movers</h1>,
    }));

    await mockCommonAppDependencies();

    await renderAppAt("/movers");

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /movers/i })).not.toBeInTheDocument();
    });
  });

  it("renders movers page content when family MVP is disabled", async () => {
    mockConfig({
      configLoaded: true,
      familyMvpEnabled: false,
      disabledTabs: [],
      tabs: {
        ...baseConfig.tabs,
        owner: true,
      },
    });

    vi.doMock("@/pages/TopMovers", () => ({
      default: () => <h1>Movers</h1>,
    }));

    await mockCommonAppDependencies();

    await renderAppAt("/movers");

    expect(await screen.findByRole("heading", { name: /movers/i })).toBeInTheDocument();
  });

  it("preserves movers fallback when family MVP has no available entry path", async () => {
    mockConfig({
      configLoaded: true,
      familyMvpEnabled: true,
      disabledTabs: ["owner", "performance", "transactions"],
      tabs: {
        ...baseConfig.tabs,
        owner: false,
        performance: false,
        transactions: false,
      },
    });

    vi.doMock("@/pages/TopMovers", () => ({
      default: () => <h1>Movers</h1>,
    }));

    await mockCommonAppDependencies();

    await renderAppAt("/movers");

    expect(await screen.findByRole("heading", { name: /movers/i })).toBeInTheDocument();
  });

  it("hides group view content when family MVP is enabled and an entry route exists", async () => {
    mockConfig({
      configLoaded: true,
      familyMvpEnabled: true,
      disabledTabs: [],
      tabs: {
        ...baseConfig.tabs,
        owner: true,
      },
    });

    vi.doMock("@/components/GroupPortfolioView", () => ({
      GroupPortfolioView: () => <section>Group Portfolio View</section>,
    }));

    await mockCommonAppDependencies();

    await renderAppAt("/?group=kids");

    await waitFor(() => {
      expect(screen.queryByText("Group Portfolio View")).not.toBeInTheDocument();
    });
  });
});
