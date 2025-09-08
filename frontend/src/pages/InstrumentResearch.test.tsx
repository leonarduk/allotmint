import { describe, it, expect, vi, beforeEach } from "vitest";
vi.mock("../hooks/useInstrumentHistory", () => ({
  useInstrumentHistory: vi.fn(),
}));
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import InstrumentResearch from "./InstrumentResearch";
import type { InstrumentDetail, ScreenerResult, NewsItem, QuoteRow } from "../types";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";
import * as api from "../api";

const mockGetInstrumentDetail = vi.spyOn(api, "getInstrumentDetail");
const mockGetScreener = vi.spyOn(api, "getScreener");
const mockGetQuotes = vi.spyOn(api, "getQuotes");
const mockGetNews = vi.spyOn(api, "getNews");
const mockUseInstrumentHistory = vi.mocked(useInstrumentHistory);

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/research/AAA"]}>
      <Routes>
        <Route path="/research/:ticker" element={<InstrumentResearch />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InstrumentResearch page", () => {
  beforeEach(() => {
    mockUseInstrumentHistory.mockReturnValue({
      data: { "30": [] },
      loading: false,
      error: null,
    } as any);
  });

  it("shows loading indicators while fetching data", async () => {
    let detailResolve: (v: InstrumentDetail) => void;
    let screenerResolve: (v: ScreenerResult[]) => void;
    let quotesResolve: (v: QuoteRow[]) => void;
    let newsResolve: (v: NewsItem[]) => void;

    mockGetInstrumentDetail.mockReturnValueOnce(
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

    expect(screen.getByText(/Loading instrument details/i)).toBeInTheDocument();
    expect(screen.getByText(/Loading metrics/i)).toBeInTheDocument();
    expect(screen.getByText(/Loading quote/i)).toBeInTheDocument();
    expect(screen.getByText(/Loading news/i)).toBeInTheDocument();

    detailResolve!({ prices: null, positions: [] } as InstrumentDetail);
    screenerResolve!([
      { rank: 1, ticker: "AAA" } as unknown as ScreenerResult,
    ]);
    quotesResolve!([
      {
        name: null,
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
    expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument();
  });

  it("renders error messages when requests fail", async () => {
    mockGetInstrumentDetail.mockRejectedValueOnce(new Error("detail fail"));
    mockGetScreener.mockRejectedValueOnce(new Error("screener fail"));
    mockGetQuotes.mockRejectedValueOnce(new Error("quotes fail"));
    mockGetNews.mockRejectedValueOnce(new Error("news fail"));

    renderPage();

    expect(await screen.findByText("detail fail")).toBeInTheDocument();
    expect(await screen.findByText("screener fail")).toBeInTheDocument();
    expect(await screen.findByText("quotes fail")).toBeInTheDocument();
    expect(await screen.findByText("news fail")).toBeInTheDocument();
  });
});

