import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { configContext, type ConfigContextValue } from "../ConfigContext";
import InstrumentResearch from "./InstrumentResearch";
import * as api from "../api";

vi.mock("../components/InstrumentHistoryChart", () => ({
  InstrumentHistoryChart: () => <div />,
}));

vi.mock("../hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: () => ({ data: {}, loading: false, error: null }),
}));

const baseConfig: ConfigContextValue = {
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: {
    group: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    screener: true,
    trading: true,
    timeseries: true,
    watchlist: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    profile: false,
    reports: true,
    scenario: true,
    logs: true,
  },
  theme: "system",
  baseCurrency: "GBP",
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
};

function renderPage(config: Partial<ConfigContextValue> = {}) {
  render(
    <configContext.Provider value={{ ...baseConfig, ...config }}>
      <MemoryRouter initialEntries={["/research/AAA"]}>
        <Routes>
          <Route path="/research/:ticker" element={<InstrumentResearch />} />
        </Routes>
      </MemoryRouter>
    </configContext.Provider>,
  );
}

describe("InstrumentResearch navigation", () => {
  let detailSpy: ReturnType<typeof vi.spyOn>;
  let screenerSpy: ReturnType<typeof vi.spyOn>;
  let newsSpy: ReturnType<typeof vi.spyOn>;
  let quotesSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    detailSpy = vi
      .spyOn(api, "getInstrumentDetail")
      .mockResolvedValue(null as any);
    screenerSpy = vi
      .spyOn(api, "getScreener")
      .mockResolvedValue([] as any);
    newsSpy = vi.spyOn(api, "getNews").mockResolvedValue([]);
    quotesSpy = vi.spyOn(api, "getQuotes").mockResolvedValue([]);
    localStorage.clear();
  });

  afterEach(() => {
    detailSpy.mockRestore();
    screenerSpy.mockRestore();
    newsSpy.mockRestore();
    quotesSpy.mockRestore();
  });

  it("shows screener and watchlist links when enabled", () => {
    renderPage();
    expect(screen.getByRole("link", { name: "View Screener" })).toHaveAttribute(
      "href",
      "/screener",
    );
    expect(screen.getByRole("link", { name: "Watchlist" })).toHaveAttribute(
      "href",
      "/watchlist",
    );
  });

  it("hides screener link when tab disabled", () => {
    renderPage({ tabs: { ...baseConfig.tabs, screener: false } });
    expect(screen.queryByRole("link", { name: "View Screener" })).toBeNull();
  });

  it("hides screener link when disabled via config", () => {
    renderPage({ disabledTabs: ["screener"] });
    expect(screen.queryByRole("link", { name: "View Screener" })).toBeNull();
  });

  it("hides watchlist link when tab disabled", () => {
    renderPage({ tabs: { ...baseConfig.tabs, watchlist: false } });
    expect(screen.queryByRole("link", { name: "Watchlist" })).toBeNull();
  });

  it("hides watchlist link when disabled via config", () => {
    renderPage({ disabledTabs: ["watchlist"] });
    expect(screen.queryByRole("link", { name: "Watchlist" })).toBeNull();
  });
});

