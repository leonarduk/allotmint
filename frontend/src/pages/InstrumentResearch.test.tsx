import { describe, it, expect, vi, beforeEach } from "vitest";
vi.mock("../hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(),
}));
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import InstrumentResearch from "./InstrumentResearch";
import type { ScreenerResult, NewsItem, QuoteRow, InstrumentDetail } from "../types";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";
import * as api from "../api";
import { configContext, type ConfigContextValue } from "../ConfigContext";

const mockFetchInstrumentDetailWithRetry = vi.spyOn(
  api,
  "fetchInstrumentDetailWithRetry",
);
const mockGetScreener = vi.spyOn(api, "getScreener");
const mockGetQuotes = vi.spyOn(api, "getQuotes");
const mockGetNews = vi.spyOn(api, "getNews");
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
    profile: true,
    pension: true,
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
      data: { mini: { "30": [] }, positions: [] },
      loading: false,
      error: null,
    } as any);
  });

  it("shows loading indicators while fetching data", async () => {
    let detailResolve: (v: InstrumentDetail) => void;
    let screenerResolve: (v: ScreenerResult[]) => void;
    let quotesResolve: (v: QuoteRow[]) => void;
    let newsResolve: (v: NewsItem[]) => void;

    mockFetchInstrumentDetailWithRetry.mockReturnValueOnce(
      new Promise((res) => {
        detailResolve = res;
      }) as Promise<InstrumentDetail>,
    );
    mockGetScreener.mockReturnValueOnce(
      new Promise((res) => {
        screenerResolve = res;
      }) as Promise<ScreenerResult[]>,
    );
    mockGetQuotes.mockReturnValueOnce(
      new Promise((res) => {
        quotesResolve = res;
      }) as Promise<QuoteRow[]>,
    );
    mockGetNews.mockReturnValueOnce(
      new Promise((res) => {
        newsResolve = res;
      }) as Promise<NewsItem[]>,
    );

    renderPage();

    expect(screen.getByText(/Loading metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/Loading quote/i)).toBeInTheDocument();
    expect(screen.getByText(/Loading news/i)).toBeInTheDocument();

    screenerResolve!([
      { rank: 1, ticker: "AAA" } as unknown as ScreenerResult,
    ]);
    quotesResolve!([
      {
        name: "Acme Corp",
        symbol: "AAA",
        last: 100,
        open: null,
        high: 110,
        low: 90,
        change: null,
        changePct: 1,
        volume: null,
        marketTime: null,
        marketState: "REGULAR",
      } as QuoteRow,
    ]);
    newsResolve!([{ headline: "headline", url: "http://example.com" }]);

    expect(await screen.findByText("Price")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "AAA - Acme Corp",
    );
    expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument();
  });

  it("renders error messages when requests fail", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: null,
      loading: false,
      error: new Error("detail fail"),
    } as any);

    mockFetchInstrumentDetailWithRetry.mockRejectedValueOnce(
      new Error("detail fail"),
    );

    mockGetScreener.mockRejectedValueOnce(new Error("screener fail"));
    mockGetQuotes.mockRejectedValueOnce(new Error("quotes fail"));
    mockGetNews.mockRejectedValueOnce(new Error("news fail"));

    renderPage();

    expect(await screen.findByText("detail fail")).toBeInTheDocument();
    expect(await screen.findByText("screener fail")).toBeInTheDocument();
    expect(await screen.findByText("quotes fail")).toBeInTheDocument();
    expect(await screen.findByText("news fail")).toBeInTheDocument();
  });

  it("shows a message when no news is available", async () => {
    mockFetchInstrumentDetailWithRetry.mockResolvedValue({
      prices: null,
      positions: [],
    } as InstrumentDetail);
    mockGetScreener.mockResolvedValue([]);
    mockGetQuotes.mockResolvedValue([]);
    mockGetNews.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("No news available")).toBeInTheDocument();
  });

  it("navigates to screener when link clicked", async () => {
    mockFetchInstrumentDetailWithRetry.mockResolvedValue({
      prices: null,
      positions: [],
    } as InstrumentDetail);
    mockGetScreener.mockResolvedValue([]);
    mockGetQuotes.mockResolvedValue([]);
    mockGetNews.mockResolvedValue([]);
    renderPage();
    const screener = screen.getByRole("link", { name: /View Screener/i });
    await userEvent.click(screener);
    expect(await screen.findByText("Screener Page")).toBeInTheDocument();
  });

  it("navigates to watchlist when link clicked", async () => {
    mockFetchInstrumentDetailWithRetry.mockResolvedValue({
      prices: null,
      positions: [],
    } as InstrumentDetail);
    mockGetScreener.mockResolvedValue([]);
    mockGetQuotes.mockResolvedValue([]);
    mockGetNews.mockResolvedValue([]);
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

  it("shows instrument name and additional metrics", async () => {
    mockFetchInstrumentDetailWithRetry.mockResolvedValue(
      { prices: null, positions: [] } as InstrumentDetail,
    );
    mockGetScreener.mockResolvedValue([
      { rank: 1, ticker: "AAA", name: "Acme Corp" } as unknown as ScreenerResult,
    ]);
    mockGetQuotes.mockResolvedValue([
      {
        name: "Acme Corp",
        symbol: "AAA",
        last: 100,
        open: null,
        high: null,
        low: null,
        change: null,
        changePct: null,
        volume: null,
        marketTime: null,
        marketState: "REGULAR",
      } as QuoteRow,
    ]);
    mockGetNews.mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByRole("heading", { level: 1 })
    ).toHaveTextContent("AAA - Acme Corp");

    const expected = [
      "Interest Coverage",
      "Current Ratio",
      "Quick Ratio",
      "FCF",
      "Gross Margin",
      "Operating Margin",
      "Net Margin",
      "EBITDA Margin",
      "ROA",
      "ROE",
      "ROI",
      "Dividend Payout Ratio",
      "Shares Outstanding",
      "Float Shares",
    ];
    for (const heading of expected) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
  });

  it("renders instrument metadata when available", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
      },
      loading: false,
      error: null,
    } as any);
    mockGetScreener.mockResolvedValue([]);
    mockGetQuotes.mockResolvedValue([]);
    mockGetNews.mockResolvedValue([]);
    renderPage();

    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("AAA - Acme Corp");
    expect(heading).toHaveTextContent("Tech");
    expect(heading).toHaveTextContent("USD");

    expect(screen.getByText(/Instrument info/i)).toBeInTheDocument();
    expect(screen.getByText(/Name:/)).toHaveTextContent("Name: Acme Corp");
    expect(screen.getByText(/Sector:/)).toHaveTextContent("Sector: Tech");
    expect(screen.getByText(/Currency:/)).toHaveTextContent("Currency: USD");
  });

  it("skips state updates when unmounted", async () => {
    mockFetchInstrumentDetailWithRetry.mockResolvedValue({
      prices: null,
      positions: [],
    } as InstrumentDetail);
    mockGetScreener.mockResolvedValue([]);
    mockGetNews.mockResolvedValue([]);

    let resolveQuotes: (rows: QuoteRow[]) => void = () => {};
    let rejectQuotes: (err: unknown) => void = () => {};
    const quotePromise = new Promise<QuoteRow[]>((resolve, reject) => {
      resolveQuotes = resolve;
      rejectQuotes = reject;
    });

    mockGetQuotes.mockImplementationOnce((_, signal) => {
      signal?.addEventListener("abort", () =>
        rejectQuotes(Object.assign(new Error("aborted"), { name: "AbortError" })),
      );
      return quotePromise;
    });

    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = renderPage();
    unmount();
    await Promise.resolve();
    resolveQuotes!([
      {
        name: "Acme Corp",
        symbol: "AAA",
        last: 1,
        open: null,
        high: null,
        low: null,
        change: null,
        changePct: null,
        volume: null,
        marketTime: null,
        marketState: "REGULAR",
      } as QuoteRow,
    ]);
    await quotePromise.catch(() => {});
    expect(errSpy).not.toHaveBeenCalledWith(
      expect.stringContaining("Can't perform a React state update on an unmounted component"),
    );
    errSpy.mockRestore();
  });
});

