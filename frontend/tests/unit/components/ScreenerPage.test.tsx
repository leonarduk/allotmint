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
});
