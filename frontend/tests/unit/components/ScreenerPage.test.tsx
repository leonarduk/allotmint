import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ScreenerPage } from "@/components/ScreenerPage";
import type { ScreenerResult } from "@/types";
import { WATCHLISTS } from "@/data/watchlists";

vi.mock("@/components/InstrumentDetail", () => ({
  InstrumentDetail: vi.fn(() => null),
}));

vi.mock("@/data/watchlists", () => ({
  WATCHLISTS: {
    "FTSE 100": ["AAA.L"],
    "FTSE 250": ["BBB.L"],
    "FTSE 350": ["AAA.L", "BBB.L"],
    "FTSE All-Share": ["AAA.L", "BBB.L"],
  },
}));

const mockGetScreener = vi.fn((tickers: string[]) =>
  Promise.resolve(
    tickers.map(
      (t, i) =>
        ({
          rank: i + 1,
          ticker: t,
          peg_ratio: null,
          pe_ratio: null,
          de_ratio: null,
          fcf: null,
          eps: null,
          gross_margin: null,
          operating_margin: null,
          net_margin: null,
          ebitda_margin: null,
          roa: null,
          roe: null,
          roi: null,
        } as ScreenerResult)
    )
  )
);

vi.mock("@/api", () => ({ getScreener: (t: string[]) => mockGetScreener(t) }));

describe("ScreenerPage", () => {
  it("renders watchlists and switches between them", async () => {
    render(<ScreenerPage />);

    const select = await screen.findByRole("combobox");
    // options present
    for (const name of Object.keys(WATCHLISTS)) {
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
    }

    await waitFor(() =>
      expect(mockGetScreener).toHaveBeenCalledWith(WATCHLISTS["FTSE 100"])
    );
    expect(await screen.findByText("AAA.L")).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "FTSE 250" } });
    await waitFor(() =>
      expect(mockGetScreener).toHaveBeenCalledWith(WATCHLISTS["FTSE 250"])
    );
    expect(await screen.findByText("BBB.L")).toBeInTheDocument();

    const selectAfter250 = await screen.findByRole("combobox");
    fireEvent.change(selectAfter250, { target: { value: "FTSE 350" } });
    await waitFor(() =>
      expect(mockGetScreener).toHaveBeenCalledWith(WATCHLISTS["FTSE 350"])
    );
    expect(await screen.findByText("AAA.L")).toBeInTheDocument();
    expect(await screen.findByText("BBB.L")).toBeInTheDocument();

    const selectAfter350 = await screen.findByRole("combobox");
    fireEvent.change(selectAfter350, { target: { value: "FTSE All-Share" } });
    await waitFor(() =>
      expect(mockGetScreener).toHaveBeenCalledWith(WATCHLISTS["FTSE All-Share"])
    );
    expect(await screen.findByText("AAA.L")).toBeInTheDocument();
  });

  it("does not emit duplicate-key warnings when the same ticker appears twice (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGetScreener.mockResolvedValue([
      { rank: 1, ticker: "CASH", name: "Cash GBP", peg_ratio: null, pe_ratio: null, de_ratio: null, fcf: null },
      { rank: 2, ticker: "CASH", name: "Cash L", peg_ratio: null, pe_ratio: null, de_ratio: null, fcf: null },
    ]);

    render(<ScreenerPage />);

    expect(await screen.findAllByText("CASH")).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key"),
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });

  it("passes instrument_type through to InstrumentDetail instead of dropping it (#6876)", async () => {
    const { InstrumentDetail } = await import("@/components/InstrumentDetail");
    mockGetScreener.mockResolvedValue([
      {
        rank: 1,
        ticker: "AAA.L",
        peg_ratio: null,
        pe_ratio: null,
        de_ratio: null,
        fcf: null,
        instrument_type: "stock",
      } as ScreenerResult,
    ]);

    render(<ScreenerPage />);

    const row = await screen.findByText("AAA.L");
    fireEvent.click(row);

    await waitFor(() =>
      expect(InstrumentDetail).toHaveBeenCalledWith(
        expect.objectContaining({ instrument_type: "stock" }),
        undefined,
      ),
    );
  });
});
