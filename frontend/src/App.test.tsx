import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mockTradingSignals = vi.fn();

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
    mockTradingSignals.mockReset();
  });

  it.skip("preselects group from URL", async () => {
    window.history.pushState({}, "", "/instrument/kids");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([
        { slug: "family", name: "Family", members: [] },
        { slug: "kids", name: "Kids", members: [] },
      ]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn(),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter initialEntries={["/instrument/kids"]}>
        <App />
      </MemoryRouter>,
    );

    const select = await screen.findByLabelText(/group/i, {
      selector: "select",
    });
    expect(select).toHaveValue("kids");
  });

  it("renders timeseries editor when path is /timeseries", async () => {
    window.history.pushState({}, "", "/timeseries?ticker=ABC&exchange=L");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter initialEntries={["/timeseries?ticker=ABC&exchange=L"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Timeseries Editor")).toBeInTheDocument();
  });

  it("renders data admin when path is /dataadmin", async () => {
    window.history.pushState({}, "", "/dataadmin");

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      listTimeseries: vi.fn().mockResolvedValue([]),
      refetchTimeseries: vi.fn(),
      rebuildTimeseriesCache: vi.fn(),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");

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

      vi.doMock("./api", () => ({
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [] }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        getTradingSignals: vi.fn().mockResolvedValue([]),
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

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
      movers: true,
      dataadmin: true,
      virtual: true,
      support: true,
      scenario: true,
    };

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...allTabs, movers: false },
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

      vi.doMock("./api", () => ({
        getOwners: vi.fn().mockResolvedValue([]),
        getGroups: vi.fn().mockResolvedValue([]),
        getGroupInstruments: vi.fn().mockResolvedValue([]),
        getPortfolio: vi.fn(),
        refreshPrices: vi.fn(),
        getAlerts: vi.fn().mockResolvedValue([]),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [] }),
        getTimeseries: vi.fn().mockResolvedValue([]),
        saveTimeseries: vi.fn(),
        getTradingSignals: mockTradingSignals,
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
      }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

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
      movers: true,
      dataadmin: true,
      virtual: true,
      support: true,
      scenario: true,
    };

    render(
      <configContext.Provider
        value={{ theme: "system", relativeViewEnabled: false, tabs: allTabs }}
      >
        <MemoryRouter initialEntries={["/movers"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    const moversTab = await screen.findByRole("link", { name: /movers/i });
    expect(moversTab).toHaveStyle("font-weight: bold");
    expect(await screen.findByText(/No signals\./i)).toBeInTheDocument();
    expect(mockTradingSignals).toHaveBeenCalled();
  });

  it("renders support page with navigation", async () => {
    window.history.pushState({}, "", "/support");

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
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

    const { default: App } = await import("./App");

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

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
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

    const { default: App } = await import("./App");

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

  it("defaults to Movers view and orders tabs correctly", async () => {
    window.history.pushState({}, "", "/");
    mockTradingSignals.mockResolvedValue([]);

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
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
        getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
        getTradingSignals: mockTradingSignals,
        listTimeseries: vi.fn().mockResolvedValue([]),
        refetchTimeseries: vi.fn(),
        rebuildTimeseriesCache: vi.fn(),
        getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    const moversLink = await screen.findByRole("link", { name: /movers/i });
    expect(moversLink).toHaveStyle("font-weight: bold");

    const nav = screen.getByRole("navigation");
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      "Movers",
      "Group",
      "Instrument",
      "Member",
      "Performance",
      "Transactions",
      "Trading",
      "Screener & Query",
      "Timeseries",
      "Watchlist",
      "Data Admin",
      "Reports",
      "Support",
      "Scenario Tester",
    ]);
  });
});
