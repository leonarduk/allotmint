import { describe, it, expect, vi, beforeEach } from "vitest";
vi.mock("@/hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(),
  getCachedInstrumentHistory: vi.fn(() => null),
}));
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import InstrumentResearch from "@/pages/InstrumentResearch";
import type { NewsItem, InstrumentMetadata } from "@/types";
import { useInstrumentHistory } from "@/hooks/useInstrumentHistory";
import * as api from "@/api";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

const mockGetNews = vi.spyOn(api, "getNews");
const mockListInstrumentMetadata = vi.spyOn(api, "listInstrumentMetadata");
const mockUpdateInstrumentMetadata = vi.spyOn(api, "updateInstrumentMetadata");
const mockGetScreener = vi.spyOn(api, "getScreener");
const mockUseInstrumentHistory = vi.mocked(useInstrumentHistory);

const defaultConfig: ConfigContextValue = {
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: {
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
    support: true,
    settings: true,
    pension: true,
    reports: true,
    scenario: true,
  },
  theme: "system",
  baseCurrency: "GBP",
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
};

function renderPage(config?: Partial<ConfigContextValue>) {
  const value: ConfigContextValue = {
    ...defaultConfig,
    ...config,
    tabs: { ...defaultConfig.tabs, ...(config?.tabs ?? {}) },
    disabledTabs: config?.disabledTabs ?? defaultConfig.disabledTabs,
  };
  return render(
    <configContext.Provider value={value}>
      <MemoryRouter initialEntries={["/research/AAA"]}>
        <Routes>
          <Route path="/" element={<div>Home</div>} />
          <Route path="/screener" element={<div>Screener Page</div>} />
          <Route path="/watchlist" element={<div>Watchlist Page</div>} />
          <Route path="/research/:ticker" element={<InstrumentResearch />} />
        </Routes>
      </MemoryRouter>
    </configContext.Provider>,
  );
}

describe("InstrumentResearch page", () => {
  beforeEach(() => {
    mockUseInstrumentHistory.mockReset();
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        prices: [
          { date: "2024-01-01", close_gbp: 100 },
          { date: "2024-01-02", close_gbp: 101 },
        ],
        rows: 2,
        from: "2024-01-01",
        to: "2024-01-02",
        base_currency: "GBP",
      },
      loading: false,
      error: null,
    } as any);
    mockListInstrumentMetadata.mockReset();
    mockUpdateInstrumentMetadata.mockReset();
    mockGetScreener.mockReset();
    mockGetNews.mockReset();
    mockGetNews.mockResolvedValue([]);
    mockGetScreener.mockResolvedValue([
      {
        rank: 1,
        ticker: "AAA.L",
        name: "Acme Corp",
        peg_ratio: 1.5,
        pe_ratio: 15.2,
        de_ratio: 0.5,
        lt_de_ratio: 0.3,
        interest_coverage: 12.5,
        current_ratio: 1.8,
        quick_ratio: 1.1,
        fcf: 250000000,
        eps: 5.25,
        gross_margin: 0.56,
        operating_margin: 0.32,
        net_margin: 0.24,
        ebitda_margin: 0.35,
        roa: 0.18,
        roe: 0.22,
        roi: 0.2,
        dividend_yield: 0.015,
        dividend_payout_ratio: 0.4,
        beta: 1.05,
        shares_outstanding: 1000000000,
        float_shares: 850000000,
        market_cap: 550000000000,
        high_52w: 320,
        low_52w: 210,
        avg_volume: 12500000,
      } as any,
    ]);
    const catalogue: InstrumentMetadata[] = [
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
      },
      {
        ticker: "BBB.N",
        exchange: "N",
        name: "Beta",
        sector: "Finance",
        currency: "USD",
      },
    ];
    mockListInstrumentMetadata.mockResolvedValue(catalogue);
    mockUpdateInstrumentMetadata.mockResolvedValue({} as any);
  });

  it("renders overview summary and defers chart to timeseries tab", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        prices: [
          { date: "2024-01-01", close_gbp: 100 },
          { date: "2024-01-02", close_gbp: 102 },
          { date: "2024-01-03", close_gbp: 104 },
          { date: "2024-01-04", close_gbp: 106 },
          { date: "2024-01-05", close_gbp: 108 },
          { date: "2024-01-08", close_gbp: 110 },
          { date: "2024-01-09", close_gbp: 112 },
          { date: "2024-01-10", close_gbp: 114 },
          { date: "2024-01-11", close_gbp: 116 },
          { date: "2024-01-12", close_gbp: 118 },
        ],
        rows: 10,
        from: "2024-01-01",
        to: "2024-01-12",
        base_currency: "GBP",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    expect(await screen.findByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Key Facts")).toBeInTheDocument();
    expect(screen.getByText("Performance")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();

    const lastCloseRow = screen.getByText("Last Close").closest("div");
    expect(lastCloseRow).not.toBeNull();
    expect(
      within(lastCloseRow as HTMLElement).getByText(/£/),
    ).toHaveTextContent("£118.00");

    const coverageRow = screen.getByText("Coverage").closest("div");
    expect(coverageRow).not.toBeNull();
    expect(
      within(coverageRow as HTMLElement).getByText("2024-01-01 → 2024-01-12"),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", { name: /Recent Prices/i }),
    ).not.toBeInTheDocument();

    const timeseriesTab = screen.getByRole("button", { name: /Timeseries/i });
    await userEvent.click(timeseriesTab);
    expect(
      await screen.findByRole("heading", { name: /Recent Prices/i }),
    ).toBeInTheDocument();
  });

  it("loads fundamentals when tab is selected", async () => {
    renderPage();
    const fundamentalsTab = screen.getByRole("button", {
      name: /Fundamentals/i,
    });
    expect(mockGetScreener).not.toHaveBeenCalled();
    await userEvent.click(fundamentalsTab);
    expect(mockGetScreener).toHaveBeenCalled();
    const [tickers, criteria, signal] = mockGetScreener.mock.calls[0] ?? [];
    expect(tickers).toEqual(["AAA"]);
    expect(criteria).toEqual({});
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(await screen.findByRole("heading", { name: "Fundamentals" })).toBeInTheDocument();
    const peRow = await screen.findByText("P/E Ratio");
    const peValue = within(peRow.closest("tr") as HTMLElement).getByText("15.20");
    expect(peValue).toBeInTheDocument();
    const netMarginRow = await screen.findByText("Net Margin");
    expect(
      within(netMarginRow.closest("tr") as HTMLElement).getByText("24.00%"),
    ).toBeInTheDocument();
  });

  it("shows fundamentals error messages", async () => {
    mockGetScreener.mockRejectedValueOnce(new Error("fundamentals fail"));

    renderPage();

    const tab = screen.getByRole("button", { name: /Fundamentals/i });
    await userEvent.click(tab);

    expect(
      await screen.findByText(/Unable to load fundamentals: fundamentals fail/),
    ).toBeInTheDocument();
  });

  it("renders error messages when requests fail", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: null,
      loading: false,
      error: new Error("detail fail"),
    } as any);
    mockGetNews.mockRejectedValueOnce(new Error("news fail"));

    renderPage();

    const positionsTab = screen.getByRole("button", { name: /Positions/i });
    await userEvent.click(positionsTab);
    expect(await screen.findByText("detail fail")).toBeInTheDocument();
    const newsTab = screen.getByRole("button", { name: /News/i });
    await userEvent.click(newsTab);
    expect(await screen.findByText("news fail")).toBeInTheDocument();
  });

  it("shows a message when no news is available", async () => {
    mockGetNews.mockResolvedValueOnce([]);

    renderPage();

    const newsTab = screen.getByRole("button", { name: /News/i });
    await userEvent.click(newsTab);
    expect(await screen.findByText("No news available")).toBeInTheDocument();
  });

  it("renders news metadata when available", async () => {
    mockGetNews.mockResolvedValueOnce([
      {
        headline: "Alpha headline",
        url: "https://example.com/alpha",
        source: "Example News",
        published_at: "2023-08-25T16:00:00Z",
      },
    ]);

    renderPage();

    const newsTab = screen.getByRole("button", { name: /News/i });
    await userEvent.click(newsTab);

    const link = await screen.findByRole("link", { name: "Alpha headline" });
    const listItem = link.closest("li");
    expect(listItem).not.toBeNull();
    const scoped = within(listItem as HTMLElement);
    expect(scoped.getByText("Example News")).toBeInTheDocument();
    expect(scoped.getByText("2023-08-25")).toBeInTheDocument();
  });

  it("navigates to screener when link clicked", async () => {
    renderPage();
    const screener = screen.getByRole("link", { name: /View Screener/i });
    await userEvent.click(screener);
    expect(await screen.findByText("Screener Page")).toBeInTheDocument();
  });

  it("navigates to watchlist when link clicked", async () => {
    renderPage();
    const watchlist = screen.getByRole("link", { name: /Watchlist/i });
    await userEvent.click(watchlist);
    expect(await screen.findByText("Watchlist Page")).toBeInTheDocument();
  });

  it("hides navigation links when corresponding tab is disabled", () => {
    renderPage({
      tabs: { screener: false, watchlist: false },
      disabledTabs: ["screener", "watchlist"],
    });
    expect(
      screen.queryByRole("link", { name: /View Screener/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Watchlist/i }),
    ).not.toBeInTheDocument();
  });

  it("reveals timeseries data and news when switching tabs", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        prices: [
          { date: "2024-01-01", close_gbp: 100 },
          { date: "2024-01-02", close_gbp: 105 },
        ],
        ticker: "AAA.L",
      },
      loading: false,
      error: null,
    } as any);
    mockGetNews.mockResolvedValueOnce([
      { headline: "headline one", url: "http://example.com" },
    ]);

    renderPage();

    expect(
      screen.queryByRole("heading", { name: /Recent Prices/i }),
    ).not.toBeInTheDocument();

    const timeseriesTab = screen.getByRole("button", { name: /Timeseries/i });
    await userEvent.click(timeseriesTab);

    expect(
      await screen.findByRole("heading", { name: /Recent Prices/i }),
    ).toBeInTheDocument();

    expect(screen.queryByText("headline one")).not.toBeInTheDocument();
    const newsTab = screen.getByRole("button", { name: /News/i });
    await userEvent.click(newsTab);
    expect(await screen.findByText("headline one")).toBeInTheDocument();
  });

  it("renders instrument metadata when available", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
        ticker: "AAA.L",
      },
      loading: false,
      error: null,
    } as any);
    renderPage();

    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /AAA - Acme Corp/,
    });
    expect(heading).toHaveTextContent("AAA - Acme Corp");
    expect(heading).toHaveTextContent("Tech");
    expect(heading).toHaveTextContent("USD");

    expect(screen.getByText(/Instrument info/i)).toBeInTheDocument();
    expect(screen.getByText(/Name:/)).toHaveTextContent("Name: Acme Corp");
    expect(screen.getByText(/Sector:/)).toHaveTextContent("Sector: Tech");
    expect(screen.getByText(/Currency:/)).toHaveTextContent("Currency: USD");
  });

  it("allows editing instrument metadata", async () => {
    renderPage();

    const editButton = await screen.findByRole("button", { name: /Edit/i });
    await userEvent.click(editButton);

    const nameInput = await screen.findByLabelText(/Name/i);
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Acme Updated");

    const sectorInput = screen.getByLabelText(/Sector/i);
    await userEvent.clear(sectorInput);
    await userEvent.type(sectorInput, "Healthcare");

    const currencySelect = screen.getByLabelText(/Currency/i);
    await userEvent.selectOptions(currencySelect, "EUR");

    const saveButton = screen.getByRole("button", { name: /Save/i });
    await userEvent.click(saveButton);

    expect(
      await screen.findByText("Instrument details updated."),
    ).toBeInTheDocument();
    expect(mockUpdateInstrumentMetadata).toHaveBeenCalledWith(
      "AAA",
      "L",
      expect.objectContaining({
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Updated",
        sector: "Healthcare",
        currency: "EUR",
      }),
    );
    expect(screen.getByText(/Name:/)).toHaveTextContent("Name: Acme Updated");
    expect(screen.getByText(/Sector:/)).toHaveTextContent("Sector: Healthcare");
    expect(screen.getByText(/Currency:/)).toHaveTextContent("Currency: EUR");
  });

  it("validates currency before saving metadata", async () => {
    renderPage();

    const editButton = await screen.findByRole("button", { name: /Edit/i });
    await userEvent.click(editButton);

    const currencySelect = screen.getByLabelText(/Currency/i);
    await userEvent.selectOptions(currencySelect, "");

    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    expect(
      await screen.findByText("Select a supported currency before saving."),
    ).toBeInTheDocument();
    expect(mockUpdateInstrumentMetadata).not.toHaveBeenCalled();
  });

  it("shows an error when saving metadata fails", async () => {
    mockUpdateInstrumentMetadata.mockRejectedValueOnce(new Error("save failed"));
    renderPage();

    const editButton = await screen.findByRole("button", { name: /Edit/i });
    await userEvent.click(editButton);

    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    expect(
      await screen.findByText("Unable to save instrument details. save failed"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Currency/i)).toBeInTheDocument();
  });

  it("surfaces catalogue load failures", async () => {
    mockListInstrumentMetadata.mockRejectedValueOnce(new Error("catalog fail"));
    renderPage();

    expect(
      await screen.findByText("Unable to load the instrument catalogue. catalog fail"),
    ).toBeInTheDocument();
  });

  it("skips news updates when unmounted", async () => {
    let rejectNews: (err: unknown) => void = () => {};
    const newsPromise = new Promise<NewsItem[]>((_, reject) => {
      rejectNews = reject;
    });

    mockGetNews.mockImplementationOnce((_, signal) => {
      signal?.addEventListener(
        "abort",
        () => rejectNews(Object.assign(new Error("aborted"), { name: "AbortError" })),
        { once: true },
      );
      return newsPromise;
    });

    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = renderPage();
    unmount();
    await newsPromise.catch(() => {});
    expect(errSpy).not.toHaveBeenCalledWith(
      expect.stringContaining("Can't perform a React state update on an unmounted component"),
    );
    errSpy.mockRestore();
  });
});
