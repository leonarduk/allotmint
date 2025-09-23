import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import i18n from "@/i18n";

const mockTradingSignals = vi.fn();

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
    mockTradingSignals.mockReset();
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

    vi.doMock("@/api", async () => {
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
    expect(mockGetGroupPortfolio).toHaveBeenCalledWith("kids");
    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenCalledWith("kids", 1, 5, 0),
    );
    await waitFor(() =>
      expect(mockGetGroupInstruments).toHaveBeenCalledWith("kids", {
        account: undefined,
        owner: undefined,
      }),
    );
  });

  it("renders timeseries editor when path is /timeseries", async () => {
    window.history.pushState({}, "", "/timeseries?ticker=ABC&exchange=L");

    vi.doMock("@/api", () => ({
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
      getCachedGroupInstruments: undefined,
    }));

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/timeseries?ticker=ABC&exchange=L"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Timeseries Editor")).toBeInTheDocument();
  });

  it("renders data admin when path is /dataadmin", async () => {
    window.history.pushState({}, "", "/dataadmin");

    vi.doMock("@/api", () => ({
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
    }));

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

      vi.doMock("@/api", () => ({
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
      }));

    const { default: App } = await import("@/App");
    const { configContext } = await import("@/ConfigContext");
    const user = userEvent.setup();

    const allTabs = {
      group: true,
      market: true,
      owner: true,
      instrument: true,
      performance: true,
      transactions: true,
      trading: true,
      screener: true,
      timeseries: true,
      watchlist: true,
      allocation: true,
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
    };

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...allTabs, movers: false },
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/movers"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    expect(screen.queryByRole("link", { name: /movers/i })).toBeNull();
  });

  it("allows navigation to enabled tabs", async () => {
    window.history.pushState({}, "", "/movers");

    mockTradingSignals.mockResolvedValue([]);

      vi.doMock("@/api", () => ({
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
      }));

    const { default: App } = await import("@/App");
    const { configContext } = await import("@/ConfigContext");
    const user = userEvent.setup();

    const allTabs = {
      group: true,
      market: true,
      owner: true,
      instrument: true,
      performance: true,
      transactions: true,
      trading: true,
      screener: true,
      timeseries: true,
      watchlist: true,
      allocation: true,
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
    };

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          refreshConfig: vi.fn(),
          setRelativeViewEnabled: () => {},
          baseCurrency: "GBP",
          setBaseCurrency: () => {},
        }}
      >
        <MemoryRouter initialEntries={["/movers"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    const menuButton = screen.getByRole("button", { name: /menu/i });
    await user.click(menuButton);

    const moversTab = await screen.findByRole("link", { name: /movers/i });
    expect(moversTab).toHaveStyle("font-weight: bold");
    expect(await screen.findByText(/No signals\./i)).toBeInTheDocument();
    expect(mockTradingSignals).toHaveBeenCalled();
  });

  it("renders support page with navigation", async () => {
    window.history.pushState({}, "", "/support");

    vi.doMock("@/api", () => ({
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
    }));

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

    vi.doMock("@/api", () => ({
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
    }));

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
    const user = userEvent.setup();

    vi.doMock("@/api", () => ({
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
    }));

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    const menuToggle = screen.getByRole("button", { name: /menu/i });
    await user.click(menuToggle);

    const groupLink = await screen.findByRole("link", { name: /group/i });
    expect(groupLink).toHaveAttribute("href", "/");
    expect(groupLink).toHaveStyle("font-weight: bold");

    const nav = screen.getByRole("navigation");
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      "Group",
      "Market Overview",
      "Movers",
      "Instrument",
      "Portfolio",
      "Performance",
      "Transactions",
      "Trading",
      "Screener & Query",
      "Timeseries",
      "Watchlist",
      "Allocation",
      "Rebalance",
      "Reports",
      "Trail",
      "Alert Settings",
      "User Settings",
      "Pension Forecast",
      "Tax Tools",
      "Scenario Tester",
      "Support",
    ]);
  });

  it("opens the research search bar and closes after navigating to a result", async () => {
    window.history.pushState({}, "", "/");

    const user = userEvent.setup();

    const searchInstruments = vi
      .fn()
      .mockResolvedValue([{ ticker: "AAA", name: "Alpha Corp" }]);

    vi.doMock("@/api", () => ({
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
      searchInstruments,
    }));

    const { default: App } = await import("@/App");

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    const researchLabel = i18n.t("app.research");
    const researchButton = screen.getByRole("button", {
      name: researchLabel,
    });
    expect(researchButton).toHaveAttribute("aria-expanded", "false");

    await user.click(researchButton);

    const searchInput = await screen.findByLabelText(/Search instruments/i);
    await user.type(searchInput, "AA");

    await new Promise((resolve) => setTimeout(resolve, 350));

    await waitFor(() => expect(searchInstruments).toHaveBeenCalledTimes(1));
    expect(searchInstruments).toHaveBeenCalledWith(
      "AA",
      undefined,
      undefined,
      expect.anything(),
    );

    const result = await screen.findByText("AAA — Alpha Corp");
    await user.click(result);

    await waitFor(() => {
      expect(researchButton).toHaveAttribute("aria-expanded", "false");
    });

    await waitFor(() => {
      expect(screen.queryByLabelText(/Search instruments/i)).not.toBeInTheDocument();
    });
  });

  it("renders the user avatar when logged in", async () => {
    window.history.pushState({}, "", "/");

    vi.doMock("@/api", () => ({
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
    }));

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
