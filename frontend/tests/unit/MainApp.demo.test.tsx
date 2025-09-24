import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

describe("MainApp demo view", () => {
  it("shows demo portfolio when only demo owner is available", async () => {
    const mockPortfolio = {
      owner: "demo",
      as_of: "2024-01-01",
      trades_this_month: 0,
      trades_remaining: 0,
      total_value_estimate_gbp: 0,
      accounts: [],
    };

    // Provide demo-mode responses from the API layer
    vi.doMock("@/api", () => ({
      getOwners: vi.fn().mockResolvedValue([
        { owner: "demo", accounts: ["isa", "sipp"] },
      ]),
      getGroups: vi.fn().mockRejectedValue(new Error("HTTP 401")),
      getGroupInstruments: vi.fn().mockResolvedValue([]),
      getPortfolio: vi.fn().mockResolvedValue(mockPortfolio),
      refreshPrices: vi.fn(),
      getAlerts: vi.fn().mockResolvedValue([]),
      getNudges: vi.fn().mockResolvedValue([]),
      getAlertSettings: vi.fn().mockResolvedValue({ threshold: 0 }),
      getCompliance: vi
        .fn()
        .mockResolvedValue({ owner: "demo", warnings: [], trade_counts: {} }),
      getTradingSignals: vi.fn().mockResolvedValue([]),
      getQuests: vi.fn().mockResolvedValue({ quests: [] }),
      getTimeseries: vi.fn(),
      saveTimeseries: vi.fn(),
      refetchTimeseries: vi.fn(),
      rebuildTimeseriesCache: vi.fn(),
      getConfig: vi.fn().mockResolvedValue({}),
    }));

    const [{ default: MainApp }, { ConfigProvider }, { RouteProvider }, { PriceRefreshProvider }] =
      await Promise.all([
        import("@/MainApp"),
        import("@/ConfigContext"),
        import("@/RouteContext"),
        import("@/PriceRefreshContext"),
      ]);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <ConfigProvider>
          <RouteProvider>
            <PriceRefreshProvider>
              <MainApp />
            </PriceRefreshProvider>
          </RouteProvider>
        </ConfigProvider>
      </MemoryRouter>,
    );

    await screen.findByText(/Refresh Prices/);
    expect(screen.queryByText(/Unauthorized/i)).toBeNull();
  });
});
