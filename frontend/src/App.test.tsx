import { render, screen, within } from "@testing-library/react";
import { Suspense } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { TabsConfig } from "./ConfigContext";

const mockTradingSignals = vi.fn();

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
    mockTradingSignals.mockReset();
  });

  const baseTabs: TabsConfig = {
    group: false,
    owner: false,
    instrument: false,
    performance: false,
    transactions: false,
    screener: false,
    timeseries: false,
    watchlist: false,
    movers: false,
    dataadmin: false,
    virtual: false,
    support: false,
    scenario: false,
    reports: false,
  };

  const allTabs: TabsConfig = {
    ...baseTabs,
    group: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    screener: true,
    timeseries: true,
    watchlist: true,
    movers: true,
    dataadmin: true,
    virtual: true,
    support: true,
    scenario: true,
    reports: true,
  };

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
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
      getTimeseries: vi.fn(),
      saveTimeseries: vi.fn(),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter initialEntries={["/instrument/kids"]}>
        <Suspense fallback={<div />}>
          <App />
        </Suspense>
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
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...baseTabs, timeseries: true },
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter initialEntries={["/timeseries?ticker=ABC&exchange=L"]}>
          <Suspense fallback={<div />}>
            <App />
          </Suspense>
        </MemoryRouter>
      </configContext.Provider>,
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
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...baseTabs, dataadmin: true },
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter initialEntries={["/dataadmin"]}>
          <Suspense fallback={<div />}>
            <App />
          </Suspense>
        </MemoryRouter>
      </configContext.Provider>,
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
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...allTabs, movers: false },
          refreshConfig: async () => {},
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
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          refreshConfig: async () => {},
        }}
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
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      listTimeseries: vi.fn().mockResolvedValue([]),
      getConfig: vi.fn().mockResolvedValue({}),
      updateConfig: vi.fn(),
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      getTradingSignals: vi.fn().mockResolvedValue([]),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...baseTabs, support: true },
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter initialEntries={["/support"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    expect(await screen.findByRole("navigation")).toBeInTheDocument();
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
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: allTabs,
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
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
      "Screener & Query",
      "Timeseries",
      "Watchlist",
      "Data Admin",
      "Support",
      "Scenario Tester",
    ]);
  });

  it("omits tabs not present in config", async () => {
    window.history.pushState({}, "", "/movers");

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      getTradingSignals: vi.fn().mockResolvedValue([]),
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...baseTabs, movers: true },
          refreshConfig: async () => {},
        }}
      >
        <MemoryRouter initialEntries={["/movers"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    expect(screen.queryByRole("link", { name: /Instrument/i })).toBeNull();
  });
});
