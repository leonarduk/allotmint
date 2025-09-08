import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import InstrumentResearch from "./InstrumentResearch";
import * as api from "../api";
import { useInstrumentHistory } from "../hooks/useInstrumentHistory";

vi.mock("../hooks/useInstrumentHistory");

const mockUseInstrumentHistory = vi.mocked(useInstrumentHistory);
const mockGetInstrumentDetail = vi.spyOn(api, "getInstrumentDetail");
const mockGetScreener = vi.spyOn(api, "getScreener");
const mockGetNews = vi.spyOn(api, "getNews");
const mockGetQuotes = vi.spyOn(api, "getQuotes");

describe("InstrumentResearch", () => {
  it("shows instrument name and metrics rows", async () => {
    mockUseInstrumentHistory.mockReturnValue({
      data: {},
      loading: false,
      error: null,
    } as any);
    mockGetInstrumentDetail.mockResolvedValue({} as any);
    mockGetScreener.mockResolvedValue([
      {
        rank: 1,
        ticker: "AAA",
        name: "Alpha Corp",
        peg_ratio: 1,
        pe_ratio: 10,
        de_ratio: 0.5,
        lt_de_ratio: 0.3,
        interest_coverage: 10,
        current_ratio: 2,
        quick_ratio: 1.5,
        fcf: 50000,
        eps: 2,
        gross_margin: 0.4,
        operating_margin: 0.2,
        net_margin: 0.1,
        ebitda_margin: 0.3,
        roa: 0.15,
        roe: 0.2,
        roi: 0.18,
        dividend_yield: 0.05,
        dividend_payout_ratio: 0.4,
        beta: 1.1,
        shares_outstanding: 1000000,
        float_shares: 800000,
        market_cap: 5000000,
        high_52w: null,
        low_52w: null,
        avg_volume: 100000,
      },
    ]);
    mockGetNews.mockResolvedValue([]);
    mockGetQuotes.mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/research/AAA"]}>
        <Routes>
          <Route path="/research/:ticker" element={<InstrumentResearch />} />
        </Routes>
      </MemoryRouter>
    );

    expect(
      await screen.findByRole("heading", { level: 1 })
    ).toHaveTextContent(/AAA.*Alpha Corp/);
    expect(await screen.findByText("Interest Coverage")).toBeInTheDocument();
    expect(screen.getByText("Current Ratio")).toBeInTheDocument();
    expect(screen.getByText("Gross Margin")).toBeInTheDocument();
    expect(screen.getByText("Shares Outstanding")).toBeInTheDocument();
  });
});
