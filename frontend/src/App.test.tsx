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
    window.history.pushState({}, "", "/movers");

    vi.mock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      getTradingSignals: vi.fn().mockResolvedValue([]),
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    const allTabs = {
      instrument: true,
      performance: true,
      transactions: true,
      screener: true,
      query: true,
      timeseries: true,
      groupInstrumentMemberTimeseries: true,
      watchlist: true,
      movers: true,
      virtual: true,
      support: true,
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
    const groupLink = await screen.findByRole("link", { name: /group/i });
    expect(groupLink).toHaveStyle("font-weight: bold");
  });

  it("shows trading signals in movers view", async () => {
    window.history.pushState({}, "", "/movers");

    mockTradingSignals.mockResolvedValue([]);

    vi.doMock("./api", () => ({
      getOwners: vi.fn().mockResolvedValue([]),
      getGroups: vi.fn().mockResolvedValue([]),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getTopMovers: vi.fn().mockResolvedValue({ gainers: [], losers: [] }),
      getPortfolio: vi.fn(),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "", warnings: [] }),
      getTimeseries: vi.fn().mockResolvedValue([]),
      saveTimeseries: vi.fn(),
      getTradingSignals: mockTradingSignals,
    }));

    const { default: App } = await import("./App");
    const { configContext } = await import("./ConfigContext");

    const allTabs = {
      instrument: true,
      performance: true,
      transactions: true,
      screener: true,
      query: true,
      timeseries: true,
      groupInstrumentMemberTimeseries: true,
      watchlist: true,
      movers: true,
      virtual: true,
      support: true,
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
});
