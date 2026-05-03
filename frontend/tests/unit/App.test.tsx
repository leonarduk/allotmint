import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, type ReactElement } from "react";
import {
  MemoryRouter,
  Link,
  RouterProvider,
  createMemoryRouter,
  useLocation,
} from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import i18n from "@/i18n";
import type { InstrumentSummary, Portfolio } from "@/types";

const mockTradingSignals = vi.fn();
const mockComplianceWarnings = vi.fn();

vi.mock("@/components/TopMoversSummary", () => ({
  TopMoversSummary: () => <div data-testid="top-movers-summary" />,
}));

vi.mock("@/components/ComplianceWarnings", () => ({
  ComplianceWarnings: ({ owners }: { owners: string[] }) => {
    mockComplianceWarnings(owners);
    return null;
  },
}));

const enabledTabs = {
  group: true,
  market: true,
  owner: true,
  instrument: true,
  performance: true,
  transactions: true,
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
  reports: true,
  scenario: true,
};

const noDisabledTabs: string[] = [];

function mockLoadedConfig(overrides: Record<string, unknown> = {}) {
  vi.doMock("../../src/ConfigContext", async () => {
    const actual = await vi.importActual<typeof import("../../src/ConfigContext")>(
      "../../src/ConfigContext",
    );
    return {
      ...actual,
      useConfig: () => ({
        configLoaded: true,
        familyMvpEnabled: false,
        disabledTabs: noDisabledTabs,
        theme: "system",
        relativeViewEnabled: false,
        tabs: enabledTabs,
        refreshConfig: vi.fn(),
        setRelativeViewEnabled: () => {},
        baseCurrency: "GBP",
        setBaseCurrency: () => {},
        enableAdvancedAnalytics: true,
        ...overrides,
      }),
    };
  });
}

function mockAppApi(factory: Parameters<typeof vi.doMock>[1]) {
  vi.doMock("../../src/api", factory);
  vi.doMock("@/api", factory);
}

async function renderWithLoadedConfig(
  ui: ReactElement,
  overrides: Record<string, unknown> = {},
) {
  const { configContext } = await import("../../src/ConfigContext");
  return render(
    <configContext.Provider
      value={{
        configLoaded: true,
        familyMvpEnabled: false,
        disabledTabs: noDisabledTabs,
        theme: "system",
        relativeViewEnabled: false,
        tabs: enabledTabs,
        refreshConfig: vi.fn(),
        setRelativeViewEnabled: () => {},
        baseCurrency: "GBP",
        setBaseCurrency: () => {},
        enableAdvancedAnalytics: true,
        ...overrides,
      }}
    >
      {ui}
    </configContext.Provider>,
  );
}

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
    mockTradingSignals.mockReset();
    mockComplianceWarnings.mockReset();
    (globalThis as any).lastRefresh = null;
  });

  it("loads the group slug from the URL", async () => {
    window.history.pushState({}, "", "/?group=kids");

    const mockGetGroupPortfolio = vi.fn().mockResolvedValue({
      name: "Kids",
      slug: "kids",
      accounts: [],
      trades_this_month: 0,
      trades_remaining: 0,
    });
    const mockGetGroupAlpha = vi
      .fn()
      .mockResolvedValue({ alpha_vs_benchmark: 0 });
    const mockGetGroupTracking = vi.fn().mockResolvedValue({ tracking_error: 0 });
    const mockGetGroupMaxDrawdown = vi
      .fn()
      .mockResolvedValue({ max_drawdown: 0 });
    const mockGetGroupSector = vi.fn().mockResolvedValue([]);
    const mockGetGroupRegion = vi.fn().mockResolvedValue([]);
    const mockGetGroupMovers = vi
      .fn()
      .mockResolvedValue({ gainers: [], losers: [] });
    const mockGetGroupInstruments = vi.fn().mockResolvedValue([]);
    const mockGetGroups = vi.fn().mockResolvedValue([
      { slug: "family", name: "Family", members: [] },
      { slug: "kids", name: "Kids", members: [] },
    ]);
    mockGetGroupPortfolio.mockName("getGroupPortfolio");
    mockGetGroups.mockName("getGroups");

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: mockGetGroups,
        getGroupPortfolio: mockGetGroupPortfolio,
        getGroupAlphaVsBenchmark: mockGetGroupAlpha,
        getGroupTrackingError: mockGetGroupTracking,
        getGroupMaxDrawdown: mockGetGroupMaxDrawdown,
        getGroupSectorContributions: mockGetGroupSector,
        getGroupRegionContributions: mockGetGroupRegion,
        getGroupMovers: mockGetGroupMovers,
        getGroupInstruments: mockGetGroupInstruments,
        getCachedGroupInstruments: undefined,
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn(),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/?group=kids"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetGroupPortfolio).toHaveBeenCalled());
    expect(mockGetGroupPortfolio).toHaveBeenCalledWith("kids", {
      asOf: undefined,
    });
    await waitFor(() =>
      expect(mockGetGroupInstruments).toHaveBeenCalledWith(
        "kids",
        {
          account_type: undefined,
          owner: undefined,
        },
        { asOf: undefined },
      ),
    );
  });

  it("loads /instrument/all rows from group holdings API", async () => {
    window.history.pushState({}, "", "/instrument/all");

    const mockGetGroupInstruments = vi.fn().mockResolvedValue([
      {
        ticker: "FOO.L",
        name: "Foo Plc",
        grouping: "Technology",
        exchange: "L",
        currency: "GBP",
        units: 10,
        market_value_gbp: 1234.56,
        gain_gbp: 100.0,
        gain_pct: 8.81,
      } as InstrumentSummary,
    ]);

    let capturedRows: InstrumentSummary[] = [];

    vi.doMock("@/components/InstrumentTable", () => ({
      InstrumentTable: ({ rows }: { rows: InstrumentSummary[] }) => {
        capturedRows = rows;
        return (
          <div data-testid="instrument-table">
            {rows.map((row) => (
              <span key={row.ticker}>{row.ticker}</span>
            ))}
          </div>
        );
      },
    }));

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi
          .fn()
          .mockResolvedValue([{ slug: "all", name: "All Instruments", members: [] }]),
        getPortfolio: vi.fn(),
        getGroupInstruments: mockGetGroupInstruments,
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
        assignInstrumentGroup: vi.fn(),
        clearInstrumentGroup: vi.fn(),
        createInstrumentGroup: vi.fn(),
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
        getCachedGroupInstruments: undefined,
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/instrument/all"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetGroupInstruments).toHaveBeenCalledTimes(1));
    expect(mockGetGroupInstruments).toHaveBeenCalledWith("all");

    const table = await screen.findByTestId("instrument-table");
    expect(within(table).getAllByText("FOO.L")).toHaveLength(1);
    expect(capturedRows[0]?.grouping).toBe("Technology");
  });

  it("loads /portfolio/all using the group portfolio endpoint", async () => {
    const mockGetPortfolio = vi.fn().mockResolvedValue({
      owner: "all",
      as_of: "2026-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);
    const mockGetGroupPortfolio = vi.fn().mockResolvedValue({
      name: "At a glance",
      slug: "all",
      accounts: [],
      trades_this_month: 0,
      trades_remaining: 0,
    });
    const mockGetGroupAlpha = vi
      .fn()
      .mockResolvedValue({ alpha_vs_benchmark: 0 });
    const mockGetGroupTracking = vi.fn().mockResolvedValue({ tracking_error: 0 });
    const mockGetGroupMaxDrawdown = vi
      .fn()
      .mockResolvedValue({ max_drawdown: 0 });
    const mockGetGroupSector = vi.fn().mockResolvedValue([]);
    const mockGetGroupRegion = vi.fn().mockResolvedValue([]);
    const mockGetGroupMovers = vi
      .fn()
      .mockResolvedValue({ gainers: [], losers: [] });

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi
          .fn()
          .mockResolvedValue([{ owner: "alex", full_name: "Alex", accounts: [] }]),
        getGroups: vi
          .fn()
          .mockResolvedValue([{ slug: "all", name: "At a glance", members: ["alex"] }]),
        getPortfolio: mockGetPortfolio,
        getGroupPortfolio: mockGetGroupPortfolio,
        getGroupAlphaVsBenchmark: mockGetGroupAlpha,
        getGroupTrackingError: mockGetGroupTracking,
        getGroupMaxDrawdown: mockGetGroupMaxDrawdown,
        getGroupSectorContributions: mockGetGroupSector,
        getGroupRegionContributions: mockGetGroupRegion,
        getGroupMovers: mockGetGroupMovers,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getCachedGroupInstruments: undefined,
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
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

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/portfolio/all"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetGroupPortfolio).toHaveBeenCalledWith("all", {
        asOf: undefined,
      }),
    );
    expect(mockGetGroupPortfolio).toHaveBeenCalledTimes(1);
    expect(mockGetPortfolio).not.toHaveBeenCalled();
    expect(mockComplianceWarnings.mock.calls).toContainEqual([["alex"]]);
  });

  it("waits for groups before treating /portfolio/all as a group route", async () => {
    let resolveGroups:
      | ((groups: { slug: string; name: string; members: string[] }[]) => void)
      | undefined;

    const mockGetPortfolio = vi.fn().mockResolvedValue({
      owner: "all",
      as_of: "2026-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    } as Portfolio);
    const mockGetGroupPortfolio = vi.fn().mockResolvedValue({
      name: "At a glance",
      slug: "all",
      accounts: [],
      trades_this_month: 0,
      trades_remaining: 0,
    });
    const groupsPromise = new Promise<
      { slug: string; name: string; members: string[] }[]
    >((resolve) => {
      resolveGroups = resolve;
    });

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi
          .fn()
          .mockResolvedValue([{ owner: "alex", full_name: "Alex", accounts: [] }]),
        getGroups: vi.fn().mockReturnValue(groupsPromise),
        getPortfolio: mockGetPortfolio,
        getGroupPortfolio: mockGetGroupPortfolio,
        getGroupAlphaVsBenchmark: vi
          .fn()
          .mockResolvedValue({ alpha_vs_benchmark: 0 }),
        getGroupTrackingError: vi.fn().mockResolvedValue({ tracking_error: 0 }),
        getGroupMaxDrawdown: vi.fn().mockResolvedValue({ max_drawdown: 0 }),
        getGroupSectorContributions: vi.fn().mockResolvedValue([]),
        getGroupRegionContributions: vi.fn().mockResolvedValue([]),
        getGroupMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getCachedGroupInstruments: undefined,
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
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

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/portfolio/all"]}>
        <App />
      </MemoryRouter>,
    );

    expect(mockGetPortfolio).not.toHaveBeenCalled();
    expect(mockGetGroupPortfolio).not.toHaveBeenCalled();

    await act(async () => {
      resolveGroups?.([{ slug: "all", name: "At a glance", members: ["alex"] }]);
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(mockGetGroupPortfolio).toHaveBeenCalledWith("all", {
        asOf: undefined,
      }),
    );
    expect(mockGetPortfolio).not.toHaveBeenCalled();
    expect(mockComplianceWarnings.mock.calls).toContainEqual([["alex"]]);
  });

  it("renders timeseries editor when path is /timeseries", async () => {
    window.history.pushState({}, "", "/timeseries?ticker=ABC&exchange=L");

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getGroupPortfolio: vi
          .fn()
          .mockResolvedValue({
            name: "Default",
            slug: "",
            accounts: [],
            trades_this_month: 0,
            trades_remaining: 0,
          }),
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
        searchInstruments: vi.fn().mockResolvedValue([]),
        getCachedGroupInstruments: undefined,
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/timeseries?ticker=ABC&exchange=L"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: /time series/i }),
    ).toBeInTheDocument();
  });

  it("renders data admin when path is /dataadmin", async () => {
    window.history.pushState({}, "", "/dataadmin");

    mockAppApi(async () => {
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
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/dataadmin"]}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Data Admin" })
    ).toBeInTheDocument();
  });

  it("hides disabled tabs and prevents navigation", async () => {
    window.history.pushState({}, "", "/movers");

    mockAppApi(async () => {
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
          .mockResolvedValue({ owner: "", warnings: [] }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi
          .fn()
          .mockResolvedValue({ gainers: [], losers: [] }),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      };
    });

    const { default: App } = await import("@/App");
    await renderWithLoadedConfig(
      <MemoryRouter initialEntries={["/movers"]}>
        <App />
      </MemoryRouter>,
      { tabs: { ...enabledTabs, movers: false } },
    );

    expect(screen.queryByRole("link", { name: /movers/i })).toBeNull();
  });

  it("keeps unknown research owner slugs without redirecting", async () => {
    window.history.pushState({}, "", "/research/MSFT");

    const locationUpdates: string[] = [];
    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    const mockGetOwners = vi
      .fn()
      .mockResolvedValue([{ owner: "alice", accounts: [] }]);
    const mockGetGroups = vi.fn().mockResolvedValue([]);
    const mockGetPortfolio = vi
      .fn()
      .mockRejectedValue(new Error("Owner not found"));
    const mockGetCompliance = vi.fn().mockResolvedValue({
      owner: "steve",
      warnings: [],
      trade_counts: {},
    });

    mockTradingSignals.mockResolvedValue([]);

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: mockGetOwners,
        getGroups: mockGetGroups,
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getGroupPortfolio: vi.fn(),
        getGroupAlphaVsBenchmark: vi.fn(),
        getGroupTrackingError: vi.fn(),
        getGroupMaxDrawdown: vi.fn(),
        getGroupSectorContributions: vi.fn(),
        getGroupRegionContributions: vi.fn(),
        getGroupMovers: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: mockGetCompliance,
        complianceForOwner: mockGetCompliance,
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        listTimeseries: vi.fn().mockResolvedValue([]),
        getTradingSignals: mockTradingSignals,
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    vi.doMock("@/pages/InstrumentResearch", () => ({
      __esModule: true,
      default: () => (
        <div>
          <Link to="/portfolio/steve">Steve – HSA</Link>
        </div>
      ),
    }));

    mockLoadedConfig();
    const { default: App } = await import("@/App");

    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/research/MSFT"]}>
        <LocationListener />
        <App />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("link", { name: /steve/i }));

    await waitFor(() => expect(locationUpdates.at(-1)).toBe("/portfolio/steve"));
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("steve"));

    expect(locationUpdates).not.toContain("/portfolio/alice");
    expect(await screen.findByText(/owner not found/i)).toBeInTheDocument();
  });

  it("stays on the portfolio route when switching owners from the portfolio page", async () => {
    window.history.pushState({}, "", "/portfolio/alice");

    const locationUpdates: string[] = [];

    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    const mockGetOwners = vi
      .fn()
      .mockResolvedValue([
        { owner: "alice", accounts: [] },
        { owner: "bob", accounts: [] },
      ]);
    const mockGetGroups = vi.fn().mockResolvedValue([]);
    const mockGetPortfolio = vi.fn().mockImplementation((owner: string) =>
      Promise.resolve({
        owner,
        as_of: "2024-01-01T00:00:00.000Z",
        trades_this_month: 0,
        trades_remaining: 0,
        total_value_estimate_gbp: 0,
        accounts: [],
      }),
    );
    const mockGetCompliance = vi.fn().mockResolvedValue({
      owner: "",
      warnings: [],
      trade_counts: {},
    });
    const mockComplianceForOwner = vi.fn().mockResolvedValue({
      owner: "",
      warnings: [],
      trade_counts: {},
    });
    const mockGetValueAtRisk = vi.fn().mockResolvedValue({ var: {} });
    const mockGetVarBreakdown = vi.fn().mockResolvedValue([]);
    const mockRecomputeValueAtRisk = vi.fn();

    mockTradingSignals.mockResolvedValue([]);

    vi.doMock("@/components/PerformanceDashboard", () => ({
      __esModule: true,
      default: () => <div data-testid="performance-dashboard" />,
    }));

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: mockGetOwners,
        getGroups: mockGetGroups,
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getGroupPortfolio: vi.fn(),
        getGroupAlphaVsBenchmark: vi.fn(),
        getGroupTrackingError: vi.fn(),
        getGroupMaxDrawdown: vi.fn(),
        getGroupSectorContributions: vi.fn(),
        getGroupRegionContributions: vi.fn(),
        getGroupMovers: vi.fn(),
        getCachedGroupInstruments: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: mockGetCompliance,
        complianceForOwner: mockComplianceForOwner,
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        listTimeseries: vi.fn().mockResolvedValue([]),
        listInstrumentMetadata: vi.fn().mockResolvedValue([]),
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
        assignInstrumentGroup: vi.fn(),
        clearInstrumentGroup: vi.fn(),
        createInstrumentGroup: vi.fn(),
        getTradingSignals: mockTradingSignals,
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getValueAtRisk: mockGetValueAtRisk,
        recomputeValueAtRisk: mockRecomputeValueAtRisk,
        getVarBreakdown: mockGetVarBreakdown,
      };
    });

    const { default: App } = await import("@/App");

    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/portfolio/alice"]}>
        <LocationListener />
        <App />
      </MemoryRouter>,
    );

    const ownerSelectorContainer = await screen.findByTestId(
      "portfolio-owner-selector",
    );
    const portfolioSelector = within(ownerSelectorContainer).getByLabelText(/owner/i);
    await waitFor(() => {
      expect((portfolioSelector as HTMLSelectElement).options.length).toBeGreaterThan(1);
    });
    await user.selectOptions(portfolioSelector as HTMLSelectElement, "bob");

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    await waitFor(() =>
      expect(locationUpdates.at(-1)?.startsWith("/portfolio")).toBe(true),
    );
    expect(locationUpdates.some((path) => path.startsWith("/performance"))).toBe(false);
  });

  it("renders a single owner selector on the portfolio page", async () => {
    window.history.pushState({}, "", "/portfolio/alice");

    const mockGetOwners = vi.fn().mockResolvedValue([
      { owner: "alice", accounts: [] },
      { owner: "bob", accounts: [] },
    ]);

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: mockGetOwners,
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn().mockResolvedValue({
          owner: "alice",
          as_of: "2024-01-01T00:00:00.000Z",
          trades_this_month: 0,
          trades_remaining: 0,
          total_value_estimate_gbp: 0,
          accounts: [],
        }),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");
    render(
      <MemoryRouter initialEntries={["/portfolio/alice"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByTestId("portfolio-owner-selector");
    await waitFor(() => {
      expect(screen.queryAllByTestId("portfolio-owner-selector")).toHaveLength(1);
    });
  });

  it("navigates to the exact encoded URL path when selecting an owner from the portfolio selector", async () => {
    // Regression test for https://github.com/leonarduk/allotmint/issues/2653
    // Asserts that the portfolio OwnerSelector (data-testid="portfolio-owner-selector") calls
    // handleOwnerSelectPortfolio, which navigates to /portfolio/<owner> and NOT just
    // updates state (the original bug: setSelectedOwner was called directly without navigate).
    window.history.pushState({}, "", "/portfolio/alice");

    const mockGetOwners = vi
      .fn()
      .mockResolvedValue([
        { owner: "alice", accounts: [] },
        { owner: "bob", accounts: [] },
      ]);
    const mockGetPortfolio = vi.fn().mockImplementation((owner: string) =>
      Promise.resolve({
        owner,
        as_of: "2024-01-01T00:00:00.000Z",
        trades_this_month: 0,
        trades_remaining: 0,
        total_value_estimate_gbp: 0,
        accounts: [],
      }),
    );

    mockTradingSignals.mockResolvedValue([]);

    const mockNavigate = vi.fn();

    vi.doMock("react-router-dom", async () => {
      const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
      return {
        ...actual,
        useNavigate: () => mockNavigate,
      };
    });

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: mockGetOwners,
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getGroupPortfolio: vi.fn(),
        getGroupAlphaVsBenchmark: vi.fn(),
        getGroupTrackingError: vi.fn(),
        getGroupMaxDrawdown: vi.fn(),
        getGroupSectorContributions: vi.fn(),
        getGroupRegionContributions: vi.fn(),
        getGroupMovers: vi.fn(),
        getCachedGroupInstruments: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        listTimeseries: vi.fn().mockResolvedValue([]),
        listInstrumentMetadata: vi.fn().mockResolvedValue([]),
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
        assignInstrumentGroup: vi.fn(),
        clearInstrumentGroup: vi.fn(),
        createInstrumentGroup: vi.fn(),
        getTradingSignals: mockTradingSignals,
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getValueAtRisk: vi.fn().mockResolvedValue({ var: {} }),
        recomputeValueAtRisk: vi.fn(),
        getVarBreakdown: vi.fn().mockResolvedValue([]),
      };
    });

    const { default: App } = await import("@/App");
    const {
      MemoryRouter: FreshMemoryRouter,
      useLocation: useFreshLocation,
    } = await import("react-router-dom");
    const user = userEvent.setup();

    render(
      <FreshMemoryRouter initialEntries={["/portfolio/alice"]}>
        <App />
      </FreshMemoryRouter>,
    );

    // Wait for owners to load and selector to be populated
    const ownerSelectorContainer = await screen.findByTestId("portfolio-owner-selector");
    const portfolioSelector = within(ownerSelectorContainer).getByLabelText(/owner/i);
    await waitFor(() => {
      expect((portfolioSelector as HTMLSelectElement).options.length).toBeGreaterThan(1);
    });

    // Select bob — this exercises handleOwnerSelectPortfolio via the portfolio selector
    await user.selectOptions(portfolioSelector as HTMLSelectElement, "bob");

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/portfolio/bob"));
    expect(mockNavigate).not.toHaveBeenCalledWith("/performance/bob");
  });

  it("redirects /portfolio to the first owner when multiple owners are available", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    expect(
      getOwnerRootRedirectPath("/portfolio", "", [
        { owner: "alice", accounts: [] },
        { owner: "bob", accounts: [] },
      ]),
    ).toBe("/portfolio/alice");
  });

  it("redirects /performance to the first owner when multiple owners are available", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    expect(
      getOwnerRootRedirectPath("/performance", "", [
        { owner: "alice", accounts: [] },
        { owner: "bob", accounts: [] },
      ]),
    ).toBe("/performance/alice");
  });

  it("stays on /portfolio when no owners are available", async () => {
    window.history.pushState({}, "", "/portfolio");
    const locationUpdates: string[] = [];

    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    const mockGetPortfolio = vi.fn();

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");
    const {
      MemoryRouter: FreshMemoryRouter,
      useLocation: useFreshLocation,
    } = await import("react-router-dom");

    function LocationListener() {
      const location = useFreshLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    render(
      <FreshMemoryRouter initialEntries={["/portfolio"]}>
        <LocationListener />
        <App />
      </FreshMemoryRouter>,
    );

    await waitFor(() => expect(locationUpdates[0]).toBe("/portfolio"));
    expect(locationUpdates).not.toContain("/portfolio/alice");
    expect(mockGetPortfolio).not.toHaveBeenCalled();
  });

  it("stays on /performance when no owners are available", async () => {
    window.history.pushState({}, "", "/performance");
    const locationUpdates: string[] = [];

    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    vi.doMock("@/components/PerformanceDashboard", () => ({
      __esModule: true,
      default: () => <div data-testid="performance-dashboard" />,
    }));

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");
    const {
      MemoryRouter: FreshMemoryRouter,
      useLocation: useFreshLocation,
    } = await import("react-router-dom");

    function LocationListener() {
      const location = useFreshLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    render(
      <FreshMemoryRouter initialEntries={["/performance"]}>
        <LocationListener />
        <App />
      </FreshMemoryRouter>,
    );

    await waitFor(() => expect(locationUpdates[0]).toBe("/performance"));
    expect(locationUpdates).not.toContain("/performance/alice");
    expect(screen.getByTestId("active-route-marker")).toHaveAttribute("data-mode", "performance");
  });

  it("redirects once owners load asynchronously on owner-root routes", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    expect(getOwnerRootRedirectPath("/portfolio", "", [])).toBeNull();
    expect(
      getOwnerRootRedirectPath("/portfolio", "", [{ owner: "alice", accounts: [] }]),
    ).toBe("/portfolio/alice");
  });

  it("redirects once owners load asynchronously on /performance root", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    expect(getOwnerRootRedirectPath("/performance", "", [])).toBeNull();
    expect(
      getOwnerRootRedirectPath("/performance", "", [{ owner: "alice", accounts: [] }]),
    ).toBe("/performance/alice");
  });

  it("keeps explicit /portfolio/:owner routes stable without overriding selected owner", async () => {
    window.history.pushState({}, "", "/portfolio/bob");
    const locationUpdates: string[] = [];

    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    const mockGetPortfolio = vi.fn().mockResolvedValue({
      owner: "bob",
      as_of: "2024-01-01T00:00:00.000Z",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    });

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([
          { owner: "alice", accounts: [] },
          { owner: "bob", accounts: [] },
        ]),
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/portfolio/bob"]}>
        <LocationListener />
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("bob"));
    expect(locationUpdates).toContain("/portfolio/bob");
    expect(locationUpdates).not.toContain("/portfolio/alice");
  });

  it("keeps explicit /performance/:owner routes stable without overriding selected owner", async () => {
    window.history.pushState({}, "", "/performance/bob");
    const locationUpdates: string[] = [];

    function LocationListener() {
      const location = useLocation();
      useEffect(() => {
        locationUpdates.push(location.pathname);
      }, [location.pathname]);
      return null;
    }

    vi.doMock("@/components/PerformanceDashboard", () => ({
      __esModule: true,
      default: ({ owner }: { owner: string }) => <div data-testid="performance-dashboard">{owner}</div>,
    }));

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: vi.fn().mockResolvedValue([
          { owner: "alice", accounts: [] },
          { owner: "bob", accounts: [] },
        ]),
        getGroups: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/performance/bob"]}>
        <LocationListener />
        <App />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("performance-dashboard")).toHaveTextContent("bob"),
    );
    expect(locationUpdates).toContain("/performance/bob");
    expect(locationUpdates).not.toContain("/performance/alice");
  });

  it("reuses cached portfolio data when returning from research", async () => {
    window.history.pushState({}, "", "/portfolio/alice");
    globalThis.AbortSignal = window.AbortSignal;

    const renderStates: Array<{ loading: boolean; owner: string | null }> = [];

    vi.doMock("@/components/PortfolioView", () => ({
      PortfolioView: ({
        data,
        loading,
      }: {
        data: Portfolio | null;
        loading?: boolean;
      }) => {
        renderStates.push({ loading: Boolean(loading), owner: data?.owner ?? null });
        return (
          <div data-testid="portfolio-view">
            {loading ? "loading" : data?.owner ?? "none"}
          </div>
        );
      },
    }));

    const mockGetOwners = vi
      .fn()
      .mockResolvedValue([{ owner: "alice", accounts: [] }]);
    const mockGetGroups = vi.fn().mockResolvedValue([]);
    const mockGetPortfolio = vi.fn().mockResolvedValue({
      owner: "alice",
      as_of: "2024-01-01T00:00:00.000Z",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    });

    mockAppApi(async () => {
      const actual = await vi.importActual<typeof import("@/api")>("@/api");
      return {
        ...actual,
        getOwners: mockGetOwners,
        getGroups: mockGetGroups,
        getPortfolio: mockGetPortfolio,
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getGroupPortfolio: vi.fn(),
        getGroupAlphaVsBenchmark: vi.fn(),
        getGroupTrackingError: vi.fn(),
        getGroupMaxDrawdown: vi.fn(),
        getGroupSectorContributions: vi.fn(),
        getGroupRegionContributions: vi.fn(),
        getGroupMovers: vi.fn(),
        getCachedGroupInstruments: vi.fn(),
        listInstrumentMetadata: vi.fn().mockResolvedValue([]),
        listInstrumentGroups: vi.fn().mockResolvedValue([]),
        listInstrumentGroupingDefinitions: vi.fn().mockResolvedValue([]),
        refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getNudges: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        complianceForOwner: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getValueAtRisk: vi.fn().mockResolvedValue({ var: {} }),
        recomputeValueAtRisk: vi.fn(),
        getVarBreakdown: vi.fn().mockResolvedValue([]),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/portfolio/alice"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledTimes(1));

    expect(await screen.findByTestId("portfolio-view")).toHaveTextContent("alice");
    expect(mockGetPortfolio).toHaveBeenCalledTimes(1);
    expect(renderStates.some((entry) => entry.loading === false && entry.owner === "alice")).toBe(true);
  });

  it("allows navigation to enabled tabs", async () => {
    window.history.pushState({}, "", "/movers");

    mockTradingSignals.mockResolvedValue([]);

    mockAppApi(async () => {
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
          .mockResolvedValue({ owner: "", warnings: [] }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        getTradingSignals: mockTradingSignals,
        getTopMovers: vi
          .fn()
          .mockResolvedValue({ gainers: [], losers: [] }),
        getGroupMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      };
    });

    const { default: App } = await import("@/App");
    await renderWithLoadedConfig(
      <MemoryRouter initialEntries={["/movers"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findAllByText("Movers")).not.toHaveLength(0);
    expect(screen.getByTestId("active-route-marker")).toHaveAttribute("data-mode", "movers");
  });

  it("renders support page with navigation", async () => {
    window.history.pushState({}, "", "/support");

    mockAppApi(async () => {
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
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getConfig: vi.fn().mockResolvedValue({}),
        updateConfig: vi.fn(),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/support"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("navigation")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: /Support/i })
    ).toBeInTheDocument();
  });

  it("adjusts layout for different viewports", async () => {
    window.history.pushState({}, "", "/support");

    mockAppApi(async () => {
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
        getCompliance: vi
          .fn()
          .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getConfig: vi.fn().mockResolvedValue({}),
        updateConfig: vi.fn(),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      };
    });

    const { default: App } = await import("@/App");

    window.innerWidth = 375;
    window.dispatchEvent(new Event("resize"));
    const { container, rerender } = render(
      <MemoryRouter initialEntries={["/support"]}>
        <App />
      </MemoryRouter>,
    );
    expect(container.querySelector(".container")).toBeTruthy();

    window.innerWidth = 1024;
    window.dispatchEvent(new Event("resize"));
    rerender(
      <MemoryRouter initialEntries={["/support"]}>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: /Support/i })
    ).toBeInTheDocument();
  });

  it("defaults to Group view and orders tabs correctly", async () => {
    window.history.pushState({}, "", "/");
    mockTradingSignals.mockResolvedValue([]);
    mockAppApi(async () => {
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
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getGroupMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getTradingSignals: mockTradingSignals,
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getGroupAlphaVsBenchmark: vi
          .fn()
          .mockResolvedValue({ alpha_vs_benchmark: 0 }),
        getGroupTrackingError: vi.fn().mockResolvedValue({ tracking_error: 0 }),
        getGroupMaxDrawdown: vi.fn().mockResolvedValue({ max_drawdown: 0 }),
        getGroupSectorContributions: vi.fn().mockResolvedValue([]),
        getGroupRegionContributions: vi.fn().mockResolvedValue([]),
        getCachedGroupInstruments: undefined,
      };
    });

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    const groupLink = await screen.findByText("Group");
    expect(groupLink).toHaveAttribute("href", "/");
    expect(groupLink).toBeInTheDocument();

    const nav = screen.getByRole("navigation");
    expect(within(nav).getByText("Market Overview")).toBeInTheDocument();
    expect(within(nav).getByText("Portfolio")).toBeInTheDocument();
    expect(within(nav).getByText("Support")).toBeInTheDocument();
  });

  it("navigates to the research page from the menu", async () => {
    window.history.pushState({}, "", "/");

    const user = userEvent.setup();

    mockAppApi(async () => {
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
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getGroupMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      };
    });

    const { default: App } = await import("@/App");
    const { MemoryRouter: FreshMemoryRouter } = await import("react-router-dom");

    render(
      <FreshMemoryRouter initialEntries={["/"]}>
        <App />
      </FreshMemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: /insights/i }));
    const researchLink = screen.getByRole("navigation").querySelector(
      'a[href="/research"]',
    ) as HTMLAnchorElement | null;
    expect(researchLink).not.toBeNull();
    expect(researchLink).toHaveAttribute("href", "/research");

    await user.click(researchLink!);

    await waitFor(() => {
      expect(screen.getByTestId("active-route-marker")).toHaveAttribute("data-mode", "research");
    });
  });

  it("renders the user avatar when logged in", async () => {
    window.history.pushState({}, "", "/");

    mockAppApi(async () => {
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
      };
    });

    const { default: App } = await import("@/App");
    const { AuthContext } = await import("@/AuthContext");

    render(
      <AuthContext.Provider
        value={{ user: { picture: "http://example.com/pic.jpg" }, setUser: vi.fn() }}
      >
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    const avatar = await screen.findByRole("img", { name: /user avatar/i });
    expect(avatar).toHaveAttribute("src", "http://example.com/pic.jpg");
  });
});
