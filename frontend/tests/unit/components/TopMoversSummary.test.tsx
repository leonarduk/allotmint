import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopMoversSummary } from "@/components/TopMoversSummary";
import type { MoverRow } from "@/types";
import moversPlugin from "@/plugins/movers";

const mockGetGroupMovers = vi.fn(() =>
  Promise.resolve({
    gainers: [
      { ticker: "AAA", name: "AAA", change_pct: 5 } as MoverRow,
      { ticker: "CCC", name: "CCC", change_pct: 2 } as MoverRow,
      { ticker: "EEE", name: "EEE", change_pct: 1 } as MoverRow,
    ],
    losers: [
      { ticker: "BBB", name: "BBB", change_pct: -3 } as MoverRow,
      { ticker: "DDD", name: "DDD", change_pct: -4 } as MoverRow,
      { ticker: "FFF", name: "FFF", change_pct: -1 } as MoverRow,
    ],
  }),
);
const mockGetTradingSignals = vi.fn(() => Promise.resolve([]));

vi.mock("@/api", () => ({
  getGroupMovers: (
    ...args: Parameters<typeof mockGetGroupMovers>
  ) => mockGetGroupMovers(...args),
  getTradingSignals: (
    ...args: Parameters<typeof mockGetTradingSignals>
  ) => mockGetTradingSignals(...args),
}));

describe("TopMoversSummary", () => {
  beforeEach(() => {
    mockGetGroupMovers.mockClear();
    mockGetTradingSignals.mockClear();
  });

  it("renders movers and view more link", async () => {
    render(
      <MemoryRouter>
        <TopMoversSummary slug="all" />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenCalledWith("all", 1, 5, 0),
    );
    expect(await screen.findByRole("button", { name: "AAA" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "DDD" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "FFF" })).not.toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view more/i });
    expect(link).toHaveAttribute("href", moversPlugin.path({ group: "all" }));
  });

  it("handles missing slug", async () => {
    render(
      <MemoryRouter>
        <TopMoversSummary />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetGroupMovers).not.toHaveBeenCalled());
    expect(screen.getByText(/no group selected/i)).toBeInTheDocument();
  });
});
