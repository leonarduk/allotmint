import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
vi.mock("@/hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(),
  getCachedInstrumentHistory: vi.fn(() => null),
  updateCachedInstrumentHistory: vi.fn(),
}));

vi.mock("@/api", () => ({
  getNews: vi.fn(),
  listInstrumentMetadata: vi.fn(),
  updateInstrumentMetadata: vi.fn(),
  createInstrumentMetadata: vi.fn(),
  refreshInstrumentMetadata: vi.fn(),
  confirmInstrumentMetadata: vi.fn(),
  resolveMorningstarId: vi.fn(() => Promise.resolve({ status: "unresolved", morningstar_id: null })),
  getScreener: vi.fn(),
  getInstrumentValuation: vi.fn(() => Promise.reject(Object.assign(new Error("gated"), { status: 402 }))),
  getInstrumentDetail: vi.fn(),
  getInstrumentIntraday: vi.fn(),
  getLiveQuotes: vi.fn(() => Promise.resolve({ quotes: {} })),
  getInstrumentFxSplit: vi.fn(() => Promise.resolve({ applicable: false })),
  searchInstruments: vi.fn(),
  getTransactions: vi.fn(),
  getSeriesReferences: vi.fn(() => Promise.resolve({ can_delete: false })),
  deleteTimeseries: vi.fn(),
  getConfig: vi.fn(),
  getOwners: vi.fn(),
  getPriceTriggers: vi.fn(),
  createPriceTrigger: vi.fn(),
  updatePriceTrigger: vi.fn(),
  deletePriceTrigger: vi.fn(),
  getInstrumentNotes: vi.fn(() => Promise.resolve([])),
  createInstrumentNote: vi.fn(),
  deleteInstrumentNote: vi.fn(),
}));
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useNavigate, useLocation } from "react-router-dom";
import InstrumentResearch from "@/pages/InstrumentResearch";
import type { NewsItem, InstrumentMetadata } from "@/types";
import { useInstrumentHistory } from "@/hooks/useInstrumentHistory";
import * as api from "@/api";
import { configContext, type ConfigContextValue } from "@/ConfigContext";

const mockGetNews = vi.mocked(api.getNews);
const mockListInstrumentMetadata = vi.mocked(api.listInstrumentMetadata);
const mockUpdateInstrumentMetadata = vi.mocked(api.updateInstrumentMetadata);
const mockCreateInstrumentMetadata = vi.mocked(api.createInstrumentMetadata);
const mockRefreshInstrumentMetadata = vi.mocked(api.refreshInstrumentMetadata);
const mockConfirmInstrumentMetadata = vi.mocked(api.confirmInstrumentMetadata);
const mockResolveMorningstarId = vi.mocked(api.resolveMorningstarId);
const mockGetScreener = vi.mocked(api.getScreener);
const mockGetInstrumentDetail = vi.mocked(api.getInstrumentDetail);
const mockGetInstrumentIntraday = vi.mocked(api.getInstrumentIntraday);
const mockSearchInstruments = vi.mocked(api.searchInstruments);
const mockGetTransactions = vi.mocked(api.getTransactions);
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
  reportingCurrency: "GBP",
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
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
    // Safety net: return an empty-array JSON response for any fetch call that
    // escapes the @/api mocks (e.g. in CI environments). All intentional API
    // calls go through the vi.mock("@/api") module above and never reach the
    // global fetch. Using mockImplementation (not mockResolvedValue) so that
    // each intercepted call receives its own fresh Response instance — a
    // single Response body can only be consumed once.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );

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
    mockCreateInstrumentMetadata.mockReset().mockResolvedValue({} as any);
    mockRefreshInstrumentMetadata.mockReset();
    mockConfirmInstrumentMetadata.mockReset();
    mockGetScreener.mockReset();
    mockGetInstrumentDetail.mockReset();
    mockGetInstrumentIntraday.mockReset();
    mockSearchInstruments.mockReset();
    mockGetNews.mockReset();
    mockGetNews.mockResolvedValue([]);
    mockGetTransactions.mockReset();
    mockGetTransactions.mockResolvedValue([]);
    mockGetInstrumentDetail.mockResolvedValue({
      prices: [
        { date: "2024-01-01", close_gbp: 100 },
        { date: "2024-01-02", close_gbp: 101 },
      ],
      positions: [],
      currency: "GBP",
    } as any);
    mockGetInstrumentIntraday.mockResolvedValue({ prices: [] });
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
      },
      changes: {},
    } as any);
    mockConfirmInstrumentMetadata.mockResolvedValue({
      status: "updated",
      metadata: {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
      },
      changes: {},
    } as any);
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
    // The alerts tab label fetches a count on every load, so the identity
    // and trigger APIs need a resolved default even when a test never opens it.
    vi.mocked(api.getConfig).mockReset().mockResolvedValue({
      disable_auth: true,
      local_login_email: null,
      demo_identity: "demo",
    } as any);
    vi.mocked(api.getOwners).mockReset().mockResolvedValue([]);
    vi.mocked(api.getPriceTriggers).mockReset().mockResolvedValue([]);
    vi.mocked(api.getLiveQuotes).mockReset().mockResolvedValue({ quotes: {} });
    vi.mocked(api.getInstrumentNotes).mockReset().mockResolvedValue([]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it("fetches a default 365d overview range on cold load", () => {
    renderPage();

    // Overview has no range selector; it must request a positive default so
    // metrics are populated before the user ever visits the Timeseries tab.
    expect(mockUseInstrumentHistory).toHaveBeenCalledWith("AAA", 365);
  });

  it("keeps the empty-ticker case on the default path (hook guard skips fetch)", () => {
    render(
      <configContext.Provider value={defaultConfig}>
        <MemoryRouter initialEntries={["/research"]}>
          <Routes>
            <Route path="/research" element={<InstrumentResearch />} />
          </Routes>
        </MemoryRouter>
      </configContext.Provider>,
    );

    // Still resolved to a positive default; the hook's own guard prevents the
    // fetch for an empty ticker (covered in useInstrumentHistory.test.ts).
    expect(mockUseInstrumentHistory).toHaveBeenCalledWith("", 365);
  });

  it("shows a chooser message and an embedded, usable search on /research without ticker (#7223)", async () => {
    render(
      <configContext.Provider value={defaultConfig}>
        <MemoryRouter initialEntries={["/research"]}>
          <Routes>
            <Route path="/research" element={<InstrumentResearch />} />
          </Routes>
        </MemoryRouter>
      </configContext.Provider>,
    );

    expect(
      await screen.findByText("Choose a ticker from search to open research."),
    ).toBeInTheDocument();

    // The empty state must offer an actual way to pick a ticker, not just
    // describe one (#7223) — the search input is embedded directly on the page.
    expect(
      await screen.findByLabelText(/Search instruments/i),
    ).toBeInTheDocument();
  });

  it("navigates to the selected ticker from the embedded empty-state search (#7223)", async () => {
    mockSearchInstruments.mockResolvedValue([{ ticker: "BBB", name: "Beta Corp" }]);
    const user = userEvent.setup();
    // react-router-dom's useNavigate is globally mocked to a stable vi.fn()
    // (see src/setupTests.ts, #4810), so assert on the navigate call rather
    // than an actual route transition. That mock is never reset between
    // tests (no clearMocks/restoreMocks in vite.config.ts), so calls from
    // earlier tests in this file would otherwise accumulate here — clear it
    // explicitly before rendering.
    const navigateSpy = vi.mocked(useNavigate)();
    navigateSpy.mockClear();

    render(
      <configContext.Provider value={defaultConfig}>
        <MemoryRouter initialEntries={["/research"]}>
          <Routes>
            <Route path="/research" element={<InstrumentResearch />} />
          </Routes>
        </MemoryRouter>
      </configContext.Provider>,
    );

    const searchInput = await screen.findByLabelText(/Search instruments/i);
    await user.type(searchInput, "BB");

    expect(await screen.findByText("BBB — Beta Corp")).toBeInTheDocument();
    await user.click(screen.getByText("BBB — Beta Corp"));

    expect(navigateSpy).toHaveBeenCalledWith("/research/BBB");
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
    const peRow = await screen.findByText("P/E Ratio (trailing)");
    const peValue = within(peRow.closest("tr") as HTMLElement).getByText("15.20");
    expect(peValue).toBeInTheDocument();
    const netMarginRow = await screen.findByText("Net Margin");
    expect(
      within(netMarginRow.closest("tr") as HTMLElement).getByText("24.00%"),
    ).toBeInTheDocument();
  });

  it("shows a live quote beside the last close in the same units", async () => {
    vi.mocked(api.getLiveQuotes).mockResolvedValue({
      quotes: {
        AAA: {
          price: 102.5,
          price_gbp: 102.5,
          currency: "GBP",
          previous_close: 101,
          change_pct: 1.4851,
          timestamp: new Date().toISOString(),
          market_state: "REGULAR",
          is_stale: false,
        },
      },
    });

    renderPage();

    const live = await screen.findByTestId("research-live-price");
    expect(live).toHaveTextContent("£102.50");
    expect(live).toHaveTextContent("+1.49%");
    expect(vi.mocked(api.getLiveQuotes)).toHaveBeenCalledWith(["AAA"], expect.anything());
    const liveRow = await screen.findByText("Live Price");
    expect(liveRow.closest("div")).toHaveTextContent("£102.50");
  });

  it("shows a USD live quote natively, like the USD history (#7219)", async () => {
    mockListInstrumentMetadata.mockResolvedValueOnce([
      { ticker: "AAA.L", exchange: "L", name: "Acme Corp", sector: "Tech", currency: "USD" } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        currency: "GBP",
        base_currency: "GBP",
        prices: [{ date: "2024-01-02", close: 400, close_gbp: 300 }],
        rows: 1,
        from: "2024-01-02",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);
    vi.mocked(api.getLiveQuotes).mockResolvedValue({
      quotes: {
        AAA: {
          price: 410,
          price_gbp: 328,
          currency: "USD",
          previous_close: 400,
          change_pct: 2.5,
          timestamp: "2024-01-03T14:30:00Z",
          market_state: "CLOSED",
          is_stale: true,
        },
      },
    });

    renderPage();

    const live = await screen.findByTestId("research-live-price");
    expect(live).toHaveTextContent("410.00 USD");
    expect(live).not.toHaveTextContent("£328");
    // market_state CLOSED: Yahoo's regular-market price is that session's close.
    const asOf = screen.getByTestId("research-price-as-of");
    expect(asOf).toHaveAttribute("data-as-of", "close");
    expect(asOf).toHaveTextContent(/Close 2024-01-0[34]/);
  });

  it("shows the stored close, labelled as a close, when there is no quote", async () => {
    renderPage();

    await screen.findByText("Last Close");
    expect(screen.queryByTestId("research-live-price")).not.toBeInTheDocument();
    const close = screen.getByTestId("research-close-price");
    expect(close).toHaveTextContent("£101.00");
    const asOf = screen.getByTestId("research-price-as-of");
    expect(asOf).toHaveAttribute("data-as-of", "close");
    expect(asOf).toHaveTextContent("Close 2024-01-02");
  });

  it("labels a fresh in-session quote as live", async () => {
    vi.mocked(api.getLiveQuotes).mockResolvedValue({
      quotes: {
        AAA: {
          price: 102.5,
          price_gbp: 102.5,
          currency: "GBP",
          previous_close: 101,
          change_pct: 1.4851,
          timestamp: new Date().toISOString(),
          market_state: "REGULAR",
          is_stale: false,
        },
      },
    });

    renderPage();

    const asOf = await screen.findByTestId("research-price-as-of");
    expect(asOf).toHaveAttribute("data-as-of", "live");
    expect(asOf.textContent).toMatch(/Live \d{2}:\d{2}/);
  });

  it("shows native GBX close values instead of GBP-normalized close_gbp", async () => {
    // detail.currency is set to "GBP" here, not "GBX", because the backend
    // forces the JSON payload's top-level `currency` field to the reporting
    // currency whenever a close_gbp column exists (routes/instrument.py
    // ~502-515) -- which is nearly always. It can never actually say "GBX"
    // for a scaled series; the metadata catalogue is the only source for a
    // genuinely native GBX label (#7219).
    mockListInstrumentMetadata.mockResolvedValueOnce([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "GBX",
      } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        currency: "GBP",
        base_currency: "GBP",
        prices: [
          { date: "2024-01-01", close: 245, close_gbp: 2.45 },
          { date: "2024-01-02", close: 250, close_gbp: 2.5 },
        ],
        rows: 2,
        from: "2024-01-01",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    const lastCloseRow = await screen.findByText("Last Close");
    expect(lastCloseRow.closest("div")).toHaveTextContent("250.00 GBX");
    expect(lastCloseRow.closest("div")).not.toHaveTextContent("£2.50");
  });

  it("keeps native USD close values instead of GBP-converted close_gbp (#7219)", async () => {
    // Regression for the review of #7219: detail.currency/base_currency
    // ("GBP") is the backend's REPORTING currency, not what `close` is
    // quoted in -- trusting it for a USD instrument would silently relabel
    // (and unit-convert) a native USD price as GBP. close (250) and
    // close_gbp (197) genuinely differ here, so the native value must win
    // and be labelled with the instrument's declared currency (USD), the
    // same way a genuinely GBX-quoted instrument keeps its native pence
    // value (see the test above).
    mockListInstrumentMetadata.mockResolvedValueOnce([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "USD",
      } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "GBP",
        base_currency: "GBP",
        prices: [
          { date: "2024-01-01", close: 245, close_gbp: 193 },
          { date: "2024-01-02", close: 250, close_gbp: 197 },
        ],
        rows: 2,
        from: "2024-01-01",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /AAA - Acme Corp/,
    });
    expect(heading).toHaveTextContent("USD");
    expect(heading).not.toHaveTextContent("Tech · GBP");

    const currencyRow = screen.getByText("Currency").closest("div");
    expect(currencyRow).not.toBeNull();
    expect(within(currencyRow as HTMLElement).getByText("USD")).toBeInTheDocument();

    const lastCloseRow = screen.getByText("Last Close").closest("div");
    expect(lastCloseRow).not.toBeNull();
    expect(lastCloseRow).toHaveTextContent("250.00 USD");
    expect(lastCloseRow).not.toHaveTextContent("£197.00");
  });

  it("keeps a sub-unit EUR close native instead of misreading it as already-GBP (#7219)", async () => {
    // Regression for a false-positive band in an earlier fix-up: a fixed
    // absolute tolerance (e.g. 0.005) for "close already equals close_gbp"
    // misfires whenever |close| * |1 - rate| falls under it. At an ordinary
    // EUR/GBP rate of ~0.92, that band covers any EUR instrument priced
    // under ~6 cents -- close 0.06 (EUR) vs close_gbp 0.0552 (GBP, a
    // genuine ~8% FX conversion) differ by only 0.0048, which a 0.005
    // absolute epsilon would wrongly call "the same value" and render as
    // "£0.06". The comparison must be relative, not absolute, so a small
    // but real conversion is never mistaken for an unconverted value.
    mockListInstrumentMetadata.mockResolvedValueOnce([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "EUR",
      } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        sector: "Tech",
        currency: "GBP",
        base_currency: "GBP",
        prices: [
          { date: "2024-01-01", close: 0.06, close_gbp: 0.0552 },
          { date: "2024-01-02", close: 0.06, close_gbp: 0.0552 },
        ],
        rows: 2,
        from: "2024-01-01",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /AAA - Acme Corp/,
    });
    expect(heading).toHaveTextContent("EUR");
    expect(heading).not.toHaveTextContent("Tech · GBP");

    const lastCloseRow = screen.getByText("Last Close").closest("div");
    expect(lastCloseRow).not.toBeNull();
    expect(lastCloseRow).toHaveTextContent("0.06 EUR");
    expect(lastCloseRow).not.toHaveTextContent("£0.06");
  });

  it("prefers the price-series currency over stale GBX metadata (#7219)", async () => {
    // Regression for #7219: the instrument metadata catalogue can say a
    // ticker is GBX (pence) while the /instrument/ price series it is
    // actually quoted from is GBP-magnitude (close === close_gbp, not
    // scaled by 100). The header, Key Facts currency and Last Close must
    // all agree with the price series (GBP), not silently adopt the stale
    // catalogue currency and mislabel a GBP number as GBX.
    mockListInstrumentMetadata.mockResolvedValueOnce([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Health Care",
        currency: "GBX",
      } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        sector: "Health Care",
        currency: "GBP",
        base_currency: "GBP",
        prices: [
          { date: "2024-01-01", close: 120.5, close_gbp: 120.5 },
          { date: "2024-01-02", close: 121.1, close_gbp: 121.1 },
        ],
        rows: 2,
        from: "2024-01-01",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /AAA - Acme Corp/,
    });
    expect(heading).toHaveTextContent("GBP");
    expect(heading).not.toHaveTextContent("GBX");

    const currencyRow = screen.getByText("Currency").closest("div");
    expect(currencyRow).not.toBeNull();
    expect(within(currencyRow as HTMLElement).getByText("GBP")).toBeInTheDocument();

    const lastCloseRow = screen.getByText("Last Close").closest("div");
    expect(lastCloseRow).not.toBeNull();
    expect(within(lastCloseRow as HTMLElement).getByText(/£121\.10/)).toBeInTheDocument();
    expect(lastCloseRow).not.toHaveTextContent("GBX");

    // The declared/metadata currency is still shown (GBX, as the catalogue
    // says) but explicitly labelled as such -- distinct from the resolved
    // price currency above (#7219). GBX is the pence unit of GBP and the
    // pipeline normalises GBX closes to pounds, so this is NOT a mismatch
    // and must not raise the "Metadata may be stale" note (#9989).
    expect(
      screen.getByText(/Declared currency \(metadata\):/),
    ).toHaveTextContent("Declared currency (metadata): GBX");
    expect(screen.queryByText(/Metadata may be stale/)).not.toBeInTheDocument();
  });

  it("still flags a genuine cross-currency catalogue mismatch (#9989)", async () => {
    mockListInstrumentMetadata.mockResolvedValueOnce([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp",
        sector: "Health Care",
        currency: "EUR",
      } as InstrumentMetadata,
    ]);
    mockUseInstrumentHistory.mockReturnValue({
      data: {
        mini: { "30": [] },
        positions: [],
        ticker: "AAA.L",
        name: "Acme Corp",
        sector: "Health Care",
        currency: "GBP",
        base_currency: "GBP",
        prices: [{ date: "2024-01-02", close: 121.1, close_gbp: 121.1 }],
        rows: 1,
        from: "2024-01-02",
        to: "2024-01-02",
      },
      loading: false,
      error: null,
    } as any);

    renderPage();

    expect(
      await screen.findByText(/Catalogue says EUR; price feed is GBP/),
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

  it("sanitizes a 402 (screener not available) instead of showing the raw backend detail (#7221)", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetScreener.mockRejectedValueOnce(
      Object.assign(
        new Error(
          "Screener is not available: This feature requires the allotmint-pro package, which is not installed in this deployment. See https://github.com/leonarduk/allotmint-pro for upgrade options.",
        ),
        { status: 402 },
      ),
    );

    renderPage();

    const tab = screen.getByRole("button", { name: /Fundamentals/i });
    await userEvent.click(tab);

    expect(
      await screen.findByText(/Fundamentals aren't available in this deployment\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/allotmint-pro/i)).not.toBeInTheDocument();
    expect(screen.queryByText("github.com", { exact: false })).not.toBeInTheDocument();
    consoleErrorSpy.mockRestore();
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

  it("orders news most-recent first regardless of API response order", async () => {
    mockGetNews.mockResolvedValueOnce([
      {
        headline: "Oldest headline",
        url: "https://example.com/oldest",
        published_at: "2023-01-01T00:00:00Z",
      },
      {
        headline: "Newest headline",
        url: "https://example.com/newest",
        published_at: "2023-08-25T16:00:00Z",
      },
      {
        headline: "Middle headline",
        url: "https://example.com/middle",
        published_at: "2023-05-01T00:00:00Z",
      },
    ]);

    renderPage();

    const newsTab = screen.getByRole("button", { name: /News/i });
    await userEvent.click(newsTab);

    const links = await screen.findAllByRole("link", {
      name: /(Oldest|Newest|Middle) headline/,
    });
    expect(links.map((link) => link.textContent)).toEqual([
      "Newest headline",
      "Middle headline",
      "Oldest headline",
    ]);
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

  it("hides navigation links when corresponding tab is disabled", async () => {
    renderPage({
      tabs: { screener: false, watchlist: false },
      disabledTabs: ["screener", "watchlist"],
    });
    // Wait for the h1 that contains the catalogue name: this element is absent
    // on initial render (displayName is null until listInstrumentMetadata
    // resolves) and only appears once the async state update has flushed,
    // making it a reliable post-fetch sentinel.
    await screen.findByRole("heading", { level: 1, name: /Acme Corp/ });
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
    expect(
      screen.getByText(/Declared currency \(metadata\):/),
    ).toHaveTextContent("Declared currency (metadata): USD");
  });

  it("links to Investing.com and Morningstar by ISIN when the catalogue has one", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme Corp", isin: "GB00BH4HKS39" },
    ] as any);
    renderPage();

    const morningstar = await screen.findByRole("link", { name: "View on Morningstar" });
    expect(morningstar).toHaveAttribute(
      "href",
      "https://global.morningstar.com/en-gb/search?query=GB00BH4HKS39",
    );
    expect(morningstar).toHaveAttribute("target", "_blank");
    expect(morningstar).toHaveAttribute("rel", "noopener noreferrer");
    const investing = screen.getByRole("link", { name: "View on Investing.com" });
    expect(investing).toHaveAttribute(
      "href",
      "https://www.investing.com/search/?q=GB00BH4HKS39",
    );
    expect(investing).toHaveAttribute("target", "_blank");
    expect(investing).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("links to the justETF profile for an ETF with an ISIN", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme ETF", isin: "IE00BL25JN58", instrument_type: "ETF" },
    ] as any);
    renderPage();

    const justEtf = await screen.findByRole("link", { name: "View on justETF" });
    expect(justEtf).toHaveAttribute(
      "href",
      "https://www.justetf.com/en/etf-profile.html?isin=IE00BL25JN58",
    );
    expect(justEtf).toHaveAttribute("target", "_blank");
    expect(justEtf).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows catalogue identifiers in the instrument info", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme ETF",
        isin: "IE00BL25JN58",
        asset_class: "equity",
        region: "Global",
        industry: null,
        price_source: { ticker: "AAA", exchange: "MI" },
      },
    ] as any);
    renderPage();

    expect(await screen.findByText("ISIN: IE00BL25JN58")).toBeInTheDocument();
    expect(screen.getByText("Exchange: L")).toBeInTheDocument();
    expect(screen.getByText("Asset class: equity")).toBeInTheDocument();
    expect(screen.getByText("Region: Global")).toBeInTheDocument();
    expect(screen.getByText("Price source: AAA.MI")).toBeInTheDocument();
    expect(screen.queryByText(/^Industry:/)).toBeNull();
  });

  it("links Morningstar straight to the saved quote page", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      {
        ticker: "AAA",
        name: "Acme Gold",
        isin: "JE00B1VS3770",
        instrumentType: "ETC",
        morningstar_id: "0P0000AATZ",
      },
    ] as any);
    mockResolveMorningstarId.mockClear();
    renderPage();

    expect(await screen.findByText("Morningstar ID: 0P0000AATZ")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View on Morningstar" })).toHaveAttribute(
      "href",
      "https://global.morningstar.com/en-gb/investments/etfs/0P0000AATZ/quote",
    );
    expect(mockResolveMorningstarId).not.toHaveBeenCalled();
  });

  it("resolves the Morningstar id when none is saved", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA.L", exchange: "L", name: "Acme", isin: "GB00BH4HKS39", instrumentType: "Equity" },
    ] as any);
    mockResolveMorningstarId.mockResolvedValueOnce({
      status: "resolved",
      morningstar_id: "0P00007WPO",
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("link", { name: "View on Morningstar" })).toHaveAttribute(
        "href",
        "https://global.morningstar.com/en-gb/investments/stocks/0P00007WPO/quote",
      ),
    );
    expect(mockResolveMorningstarId).toHaveBeenCalledWith("AAA", "L");
  });

  it("keeps the Morningstar search link when the id lookup fails", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA.L", exchange: "L", name: "Acme", isin: "GB00BH4HKS39", instrumentType: "Equity" },
    ] as any);
    mockResolveMorningstarId.mockRejectedValueOnce(new Error("offline"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    renderPage();

    await waitFor(() => expect(warn).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "View on Morningstar" })).toHaveAttribute(
      "href",
      "https://global.morningstar.com/en-gb/search?query=GB00BH4HKS39",
    );
    warn.mockRestore();
  });

  it("links ETN instruments to their justETF profile", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme", isin: "JE00B1VS3770", instrumentType: "ETN" },
    ] as any);
    renderPage();

    expect(await screen.findByRole("link", { name: "View on justETF" })).toHaveAttribute(
      "href",
      "https://www.justetf.com/en/etf-profile.html?isin=JE00B1VS3770",
    );
  });

  it("links ETCs to their justETF profile", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme Gold", isin: "JE00B1VS3770", instrumentType: "ETC" },
    ] as any);
    renderPage();

    expect(await screen.findByRole("link", { name: "View on justETF" })).toHaveAttribute(
      "href",
      "https://www.justetf.com/en/etf-profile.html?isin=JE00B1VS3770",
    );
  });

  it("hides the justETF link for an ETF without an ISIN", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme ETF", instrumentType: "ETF" },
    ] as any);
    renderPage();

    expect(await screen.findByText("ISIN: —")).toBeInTheDocument();
    await screen.findByRole("link", { name: "View on Investing.com" });
    expect(screen.queryByRole("link", { name: "View on justETF" })).toBeNull();
  });

  it("hides the justETF link for non-ETF instruments", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme Corp", isin: "GB00BH4HKS39", instrument_type: "Equity" },
    ] as any);
    renderPage();

    expect(
      await screen.findByRole("link", { name: "View on Morningstar" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View on justETF" })).toBeNull();
  });

  it("falls back to a ticker search and hides Morningstar without an ISIN", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme Corp" },
    ] as any);
    renderPage();

    expect(
      await screen.findByRole("link", { name: "View on Investing.com" }),
    ).toHaveAttribute("href", "https://www.investing.com/search/?q=AAA");
    expect(screen.queryByRole("link", { name: "View on Morningstar" })).toBeNull();
  });

  it("clears the ISIN links when the ticker changes to one without an ISIN", async () => {
    mockListInstrumentMetadata.mockResolvedValue([
      { ticker: "AAA", name: "Acme Corp", isin: "GB00BH4HKS39" },
    ] as any);
    const tree = (ticker: string) => (
      <configContext.Provider value={defaultConfig}>
        <MemoryRouter>
          <InstrumentResearch ticker={ticker} />
        </MemoryRouter>
      </configContext.Provider>
    );
    const { rerender } = render(tree("AAA"));
    expect(
      await screen.findByRole("link", { name: "View on Morningstar" }),
    ).toBeInTheDocument();

    rerender(tree("BBB"));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "View on Investing.com" })).toHaveAttribute(
        "href",
        "https://www.investing.com/search/?q=BBB",
      ),
    );
    expect(screen.queryByRole("link", { name: "View on Morningstar" })).toBeNull();
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
      false,
    );
    // An unchanged (blank) ISIN is left out so it can't overwrite a stored one.
    expect(mockUpdateInstrumentMetadata.mock.calls[0][2]).not.toHaveProperty("isin");
    expect(mockCreateInstrumentMetadata).not.toHaveBeenCalled();
    expect(screen.getByText(/Name:/)).toHaveTextContent("Name: Acme Updated");
    expect(screen.getByText(/Sector:/)).toHaveTextContent("Sector: Healthcare");
    expect(
      screen.getByText(/Declared currency \(metadata\):/),
    ).toHaveTextContent("Declared currency (metadata): EUR");
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

  it("creates the instrument when it has no metadata yet (#10005)", async () => {
    mockUpdateInstrumentMetadata.mockRejectedValueOnce(
      Object.assign(new Error("Instrument not found"), { status: 404 }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /Edit/i }));
    await userEvent.type(screen.getByLabelText("ISIN"), "ie00bsplc298");
    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    expect(
      await screen.findByText("Instrument created. Use Refresh prices to load its price history."),
    ).toBeInTheDocument();
    expect(mockCreateInstrumentMetadata).toHaveBeenCalledWith(
      "AAA",
      "L",
      expect.objectContaining({ ticker: "AAA.L", isin: "IE00BSPLC298" }),
      false,
    );
    expect(screen.getByText(/ISIN:/)).toHaveTextContent("ISIN: IE00BSPLC298");
  });

  it("rejects a malformed ISIN before saving", async () => {
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /Edit/i }));
    await userEvent.type(screen.getByLabelText("ISIN"), "IE00BAD");
    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    expect(
      await screen.findByText(
        "Enter a 12-character ISIN (e.g. IE00BSPLC298) or leave it blank.",
      ),
    ).toBeInTheDocument();
    expect(mockUpdateInstrumentMetadata).not.toHaveBeenCalled();
  });

  it("offers the foreign-ISIN override after a 422 and resends with it", async () => {
    mockUpdateInstrumentMetadata.mockRejectedValueOnce(
      Object.assign(new Error("ISIN IE00BSPLC298 has country prefix IE"), { status: 422 }),
    );
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /Edit/i }));
    await userEvent.type(screen.getByLabelText("ISIN"), "IE00BSPLC298");
    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    const override = await screen.findByRole("checkbox", {
      name: /country differs from the exchange/i,
    });
    expect(mockUpdateInstrumentMetadata).toHaveBeenLastCalledWith(
      "AAA",
      "L",
      expect.objectContaining({ isin: "IE00BSPLC298" }),
      false,
    );

    await userEvent.click(override);
    await userEvent.click(screen.getByRole("button", { name: /Save/i }));

    expect(await screen.findByText("Instrument details updated.")).toBeInTheDocument();
    expect(mockUpdateInstrumentMetadata).toHaveBeenLastCalledWith(
      "AAA",
      "L",
      expect.objectContaining({ isin: "IE00BSPLC298" }),
      true,
    );
  });

  it("refresh populates metadata fields and applies confirmed changes", async () => {
    const user = userEvent.setup();
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp PLC",
        sector: "Technology",
        currency: "GBP",
        instrument_type: "EQUITY",
      },
      changes: {
        name: { from: "Acme Corp", to: "Acme Corp PLC" },
        currency: { from: "USD", to: "GBP" },
        instrument_type: { from: null, to: "EQUITY" },
      },
    } as any);
    mockConfirmInstrumentMetadata.mockResolvedValue({
      status: "updated",
      metadata: {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp PLC",
        sector: "Technology",
        currency: "GBP",
        instrument_type: "EQUITY",
      },
      changes: {},
    } as any);

    renderPage();

    await screen.findByText("Instrument info");

    await user.click(screen.getByRole("button", { name: /^refresh$/i }));

    expect(mockRefreshInstrumentMetadata).toHaveBeenCalledWith("AAA", "L");

    const confirmButton = await screen.findByRole("button", { name: /confirm/i });
    expect(confirmButton).toBeInTheDocument();

    const nameInput = screen.getByLabelText("Name");
    expect(nameInput).toHaveValue("Acme Corp PLC");
    expect(nameInput).toBeDisabled();

    await user.click(confirmButton);

    expect(mockConfirmInstrumentMetadata).toHaveBeenCalledWith("AAA", "L");

    expect(
      await screen.findByText("Instrument details refreshed from Yahoo Finance."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Name: Acme Corp PLC/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
  });

  it("keeps the ISIN editable during a refresh preview and saves it on confirm", async () => {
    const user = userEvent.setup();
    const refreshed = {
      ticker: "AAA.L",
      exchange: "L",
      name: "Acme Corp PLC",
      sector: "Technology",
      currency: "GBP",
      instrument_type: "EQUITY",
    };
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: refreshed,
      changes: {},
    } as any);
    mockConfirmInstrumentMetadata.mockResolvedValue({
      status: "updated",
      metadata: refreshed,
      changes: {},
    } as any);

    renderPage();

    await screen.findByText("Instrument info");
    await user.click(screen.getByRole("button", { name: /^refresh$/i }));
    await screen.findByRole("button", { name: /confirm/i });

    const preview = screen.getByText("Proposed updates").parentElement as HTMLElement;
    expect(preview.style.background).toBe("var(--surface-card-bg)");
    expect(preview.style.color).toBe("var(--surface-card-color)");

    const isinInput = screen.getByLabelText("ISIN");
    expect(isinInput).toBeEnabled();
    expect(screen.getByLabelText("Name")).toBeDisabled();
    await user.type(isinInput, "gb0001738615");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(
      await screen.findByText("Instrument details refreshed from Yahoo Finance."),
    ).toBeInTheDocument();
    expect(mockConfirmInstrumentMetadata).toHaveBeenCalledWith("AAA", "L");
    expect(mockUpdateInstrumentMetadata).toHaveBeenCalledWith(
      "AAA",
      "L",
      expect.objectContaining({ isin: "GB0001738615" }),
      false,
    );
    expect(screen.getByText(/ISIN:/)).toHaveTextContent("ISIN: GB0001738615");
  });

  it("keeps the editor open with the foreign-ISIN override when a refresh ISIN is rejected", async () => {
    const user = userEvent.setup();
    const refreshed = { ticker: "AAA.L", exchange: "L", name: "Acme Corp PLC", currency: "GBP" };
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: refreshed,
      changes: {},
    } as any);
    mockConfirmInstrumentMetadata.mockResolvedValue({
      status: "updated",
      metadata: refreshed,
      changes: {},
    } as any);
    mockUpdateInstrumentMetadata.mockRejectedValueOnce(
      Object.assign(new Error("ISIN IE00BSPLC298 has country prefix IE"), { status: 422 }),
    );

    renderPage();

    await screen.findByText("Instrument info");
    await user.click(screen.getByRole("button", { name: /^refresh$/i }));
    await screen.findByRole("button", { name: /confirm/i });
    await user.type(screen.getByLabelText("ISIN"), "IE00BSPLC298");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    const override = await screen.findByRole("checkbox", {
      name: /country differs from the exchange/i,
    });
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText("ISIN")).toHaveValue("IE00BSPLC298");

    await user.click(override);
    await user.click(screen.getByRole("button", { name: /Save/i }));

    expect(await screen.findByText("Instrument details updated.")).toBeInTheDocument();
    expect(mockUpdateInstrumentMetadata).toHaveBeenLastCalledWith(
      "AAA",
      "L",
      expect.objectContaining({ isin: "IE00BSPLC298" }),
      true,
    );
  });

  it("rejects a malformed ISIN before confirming a refresh", async () => {
    const user = userEvent.setup();
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: { ticker: "AAA.L", exchange: "L", name: "Acme Corp PLC", currency: "GBP" },
      changes: {},
    } as any);

    renderPage();

    await screen.findByText("Instrument info");
    await user.click(screen.getByRole("button", { name: /^refresh$/i }));
    await screen.findByRole("button", { name: /confirm/i });
    await user.type(screen.getByLabelText("ISIN"), "GB00BAD");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(
      await screen.findByText(
        "Enter a 12-character ISIN (e.g. IE00BSPLC298) or leave it blank.",
      ),
    ).toBeInTheDocument();
    expect(mockConfirmInstrumentMetadata).not.toHaveBeenCalled();
    expect(mockUpdateInstrumentMetadata).not.toHaveBeenCalled();
  });

  it("cancel refresh leaves metadata unchanged", async () => {
    const user = userEvent.setup();
    mockRefreshInstrumentMetadata.mockResolvedValue({
      status: "preview",
      metadata: {
        ticker: "AAA.L",
        exchange: "L",
        name: "Acme Corp PLC",
        sector: "Technology",
        currency: "GBP",
        instrument_type: "EQUITY",
      },
      changes: {
        name: { from: "Acme Corp", to: "Acme Corp PLC" },
      },
    } as any);

    renderPage();

    await screen.findByText("Instrument info");
    await user.click(screen.getByRole("button", { name: /^refresh$/i }));

    expect(await screen.findByRole("button", { name: /confirm/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mockConfirmInstrumentMetadata).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Name: Acme Corp/)).toBeInTheDocument();
  });

  it("surfaces catalogue load failures", async () => {
    mockListInstrumentMetadata.mockRejectedValueOnce(new Error("catalog fail"));
    renderPage();

    expect(
      await screen.findByText("Unable to load the instrument catalogue. catalog fail"),
    ).toBeInTheDocument();
  });

  it("adds a price alert for the resolved TICKER.EXCHANGE from the alerts tab", async () => {
    const aaaAlert = {
      id: "t1",
      ticker: "AAA.L",
      condition: "below" as const,
      price: 90,
      mode: "once" as const,
      enabled: true,
      note: null,
      created_at: "2026-01-01T00:00:00Z",
      last_triggered_at: null,
      last_triggered_price: null,
      trigger_count: 0,
    };
    const rows = [aaaAlert, { ...aaaAlert, id: "t2", ticker: "BBB.N", price: 5 }];
    vi.mocked(api.getPriceTriggers).mockImplementation(async () => [...rows]);
    const mockCreate = vi.mocked(api.createPriceTrigger).mockImplementation(async () => {
      const created = { ...aaaAlert, id: "t3", condition: "above" as const, price: 120 };
      rows.push(created);
      return created;
    });

    renderPage();
    await screen.findByRole("heading", { level: 1, name: /AAA - Acme Corp/ });
    // Only AAA.L's alert counts towards the tab label, before the tab is opened.
    const tab = await screen.findByRole("button", { name: "Price alerts (1)" });
    await userEvent.click(tab);

    expect(await screen.findByText(/Falls to or below £90\.00/)).toBeInTheDocument();
    expect(screen.queryByText(/£5\.00/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ticker")).not.toBeInTheDocument();
    expect(screen.getByText("Latest price: £101.00")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Price (£)"), "120");
    await userEvent.click(screen.getByRole("button", { name: "Add trigger" }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith("demo", {
        ticker: "AAA.L",
        condition: "above",
        price: 120,
        mode: "once",
        note: null,
      }),
    );
    // The panel reloads after saving; the label follows without a page refresh.
    expect(await screen.findByRole("button", { name: "Price alerts (2)" })).toBeInTheDocument();
  });

  it("adds a stance-tagged note with the current price from the notes tab", async () => {
    const existing = {
      id: "n1",
      ticker: "AAA.L",
      stance: "bearish" as const,
      text: "Margins look stretched",
      price: 80,
      created_at: "2026-01-01T00:00:00Z",
    };
    const rows = [existing];
    vi.mocked(api.getInstrumentNotes).mockImplementation(async () => [...rows]);
    const mockCreate = vi.mocked(api.createInstrumentNote).mockImplementation(async (_user, input) => {
      const created = { ...existing, ...input, id: "n2", price: input.price ?? null };
      rows.unshift(created);
      return created;
    });

    renderPage();
    await screen.findByRole("heading", { level: 1, name: /AAA - Acme Corp/ });
    const tab = await screen.findByRole("button", { name: "Research notes (1)" });
    await userEvent.click(tab);

    expect(await screen.findByText("Margins look stretched")).toBeInTheDocument();
    expect(api.getInstrumentNotes).toHaveBeenCalledWith("demo", "AAA.L");
    // Price then vs latest GBP close (101): +26.3%.
    expect(screen.getByText(/at £80\.00 · \+26\.3% since/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Note"), "Results beat, upgrading");
    await userEvent.selectOptions(screen.getByLabelText("Stance"), "bullish");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith("demo", {
        ticker: "AAA.L",
        stance: "bullish",
        text: "Results beat, upgrading",
        price: 101,
      }),
    );
    expect(await screen.findByRole("button", { name: "Research notes (2)" })).toBeInTheDocument();
    expect(screen.getByLabelText("Note")).toHaveValue("");
  });

  it("refuses to create alerts on a bare ticker when the exchange is unknown", async () => {
    mockListInstrumentMetadata.mockResolvedValue([]);
    mockUseInstrumentHistory.mockReturnValue({
      data: { mini: { "30": [] }, positions: [], ticker: "AAA", prices: [] },
      loading: false,
      error: null,
    } as any);

    renderPage();
    await waitFor(() => expect(mockListInstrumentMetadata).toHaveBeenCalled());
    await userEvent.click(screen.getAllByRole("button", { name: "Price alerts" })[0]);

    expect(
      await screen.findByText(/Price alerts need the instrument's exchange/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add trigger" })).not.toBeInTheDocument();
    expect(api.getPriceTriggers).not.toHaveBeenCalled();
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
  describe("compare tickers in the URL", () => {
    function LocationSearch() {
      return <div data-testid="location-search">{useLocation().search}</div>;
    }

    const renderAt = (entry: string) =>
      render(
        <configContext.Provider value={defaultConfig}>
          <MemoryRouter initialEntries={[entry]}>
            <Routes>
              <Route
                path="/research/:ticker"
                element={
                  <>
                    <InstrumentResearch />
                    <LocationSearch />
                  </>
                }
              />
            </Routes>
          </MemoryRouter>
        </configContext.Provider>,
      );

    it("opens a shared comparison link on the timeseries tab", async () => {
      renderAt("/research/AAA?compare=bbb.l,AAA,bbb.l");

      expect(await screen.findByLabelText("Remove BBB.L")).toBeInTheDocument();
      expect(screen.queryByLabelText("Remove AAA")).not.toBeInTheDocument();
      expect(mockGetInstrumentDetail).toHaveBeenCalledWith(
        "BBB.L",
        expect.any(Number),
        expect.any(AbortSignal),
      );
    });

    it("writes added and removed tickers back to the URL", async () => {
      renderAt("/research/AAA");
      await userEvent.click(screen.getByRole("button", { name: /Timeseries/i }));

      await userEvent.type(
        await screen.findByLabelText(/Compare with/),
        "BBB.L{Enter}",
      );
      await waitFor(() =>
        expect(screen.getByTestId("location-search")).toHaveTextContent(
          "?compare=BBB.L",
        ),
      );

      await userEvent.click(await screen.findByLabelText("Remove BBB.L"));
      await waitFor(() =>
        expect(screen.getByTestId("location-search")).toBeEmptyDOMElement(),
      );
    });
  });
});
