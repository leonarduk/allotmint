import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mockTradingSignals = vi.fn();

// Dynamic import after setting location and mocking APIs

describe("App", () => {
  beforeEach(() => {
    vi.resetModules();
    mockTradingSignals.mockReset();
  });

  it("defaults to movers view and orders tabs", async () => {
    window.history.pushState({}, "", "/");

    vi.mock("./api", () => ({
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
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
    }));

    const { default: App } = await import("./App");

    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("link", { name: /movers/i });
    const tabs = container.querySelectorAll("nav a");
    const labels = Array.from(tabs).map((el) => el.textContent);
    expect(labels).toEqual([
      "Movers",
      "Group",
      "Instrument",
      "Member",
      "Performance",
      "Transactions",
      "Screener",
      "Query",
      "Trading",
      "Timeseries",
      "Member Timeseries",
      "Watchlist",
      "Support",
    ]);
    expect(tabs[0]).toHaveStyle("font-weight: bold");
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
      getCompliance: vi.fn().mockResolvedValue({ owner: "", warnings: [], trade_counts: {} }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
    }));

    const { default: App } = await import("./App");

    render(
      <MemoryRouter initialEntries={["/timeseries?ticker=ABC&exchange=L"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Timeseries Editor")).toBeInTheDocument();
  });

  it("hides disabled tabs and prevents navigation", async () => {
    window.history.pushState({}, "", "/trading");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      getTradingSignals: vi.fn().mockResolvedValue([]),
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    const allTabs = {
      instrument: true,
      performance: true,
      transactions: true,
      screener: true,
      query: true,
      trading: true,
      timeseries: true,
      groupInstrumentMemberTimeseries: true,
      watchlist: true,
      virtual: true,
      support: true,
      movers: true,
    };

    render(
      <configContext.Provider
        value={{
          theme: "system",
          relativeViewEnabled: false,
          tabs: { ...allTabs, trading: false },
        }}
      >
        <MemoryRouter initialEntries={["/trading"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    expect(screen.queryByRole("link", { name: /trading/i })).toBeNull();
    const moversLink = await screen.findByRole("link", { name: /movers/i });
    expect(moversLink).toHaveStyle("font-weight: bold");
  });

  it("allows navigation to enabled tabs", async () => {
    window.history.pushState({}, "", "/trading");

    mockTradingSignals.mockResolvedValue([]);

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      getTradingSignals: mockTradingSignals,
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    const allTabs = {
      instrument: true,
      performance: true,
      transactions: true,
      screener: true,
      query: true,
      trading: true,
      timeseries: true,
      groupInstrumentMemberTimeseries: true,
      watchlist: true,
      virtual: true,
      support: true,
      movers: true,
    };

    render(
      <configContext.Provider
        value={{ theme: "system", relativeViewEnabled: false, tabs: allTabs }}
      >
        <MemoryRouter initialEntries={["/trading"]}>
          <App />
        </MemoryRouter>
      </configContext.Provider>,
    );

    const tradingTab = await screen.findByRole("link", { name: /trading/i });
    expect(tradingTab).toHaveStyle("font-weight: bold");
    expect(await screen.findByText(/No signals\./i)).toBeInTheDocument();
    expect(mockTradingSignals).toHaveBeenCalled();
  });
});
