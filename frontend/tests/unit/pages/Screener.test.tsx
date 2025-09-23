import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Screener } from "@/pages/Screener";
import * as api from "@/api";

vi.mock("@/api");

const mockGetScreener = vi.mocked(api.getScreener);

describe("Screener", () => {
  it("renders new ratio columns", async () => {
    mockGetScreener.mockResolvedValueOnce([
      {
        rank: 1,
        ticker: "AAA",
        name: "AAA Corp",
        peg_ratio: 1,
        pe_ratio: 10,
        de_ratio: 0.5,
        lt_de_ratio: 0.3,
        interest_coverage: 10,
        current_ratio: 2,
        quick_ratio: 1.5,
        fcf: 1000,
        eps: null,
        gross_margin: null,
        operating_margin: null,
        net_margin: null,
        ebitda_margin: null,
        roa: null,
        roe: null,
        roi: null,
        dividend_yield: null,
        dividend_payout_ratio: null,
        beta: null,
        shares_outstanding: null,
        float_shares: null,
        market_cap: null,
        high_52w: null,
        low_52w: null,
        avg_volume: null,
      },
    ]);

    render(<Screener />);

    fireEvent.change(screen.getByLabelText(/Tickers/i), { target: { value: "AAA" } });
    fireEvent.change(screen.getByLabelText(/Max LT D\/E/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Min Interest Coverage/i), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText(/Min Current Ratio/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Min Quick Ratio/i), { target: { value: "1" } });

    fireEvent.submit(screen.getByText(/Run/i).closest("form")!);

    await waitFor(() => expect(mockGetScreener).toHaveBeenCalled());
    expect(mockGetScreener).toHaveBeenCalledWith(
      ["AAA"],
      expect.objectContaining({
        lt_de_max: 1,
        interest_coverage_min: 5,
        current_ratio_min: 1,
        quick_ratio_min: 1,
      })
    );

    expect(await screen.findByText("LT D/E")).toBeInTheDocument();
    expect(screen.getByText("IntCov")).toBeInTheDocument();
    expect(screen.getByText("Curr")).toBeInTheDocument();
    expect(screen.getByText("Quick")).toBeInTheDocument();

    expect(screen.getByText("0.3")).toBeInTheDocument();
    expect(screen.getAllByText("10")).toHaveLength(2);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1.5")).toBeInTheDocument();
  });
});

