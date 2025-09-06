import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../api", () => ({
  getQuotes: vi.fn(),
}));

import { Watchlist } from "./Watchlist";
import { getQuotes } from "../api";
import type { QuoteRow } from "../types";

const sampleRows: QuoteRow[] = [
  {
    name: "Alpha",
    symbol: "AAA",
    last: 10,
    open: 9,
    high: 11,
    low: 8,
    change: 1,
    changePct: 10,
    volume: 1000,
    marketTime: "2024-01-01T00:00:00Z",
    marketState: "REGULAR",
  },
  {
    name: "Beta",
    symbol: "BBB",
    last: 5,
    open: 6,
    high: 6,
    low: 4,
    change: -1,
    changePct: -20,
    volume: 2000,
    marketTime: "2024-01-01T01:00:00Z",
    marketState: "REGULAR",
  },
];

describe("Watchlist page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders quotes and sorts columns", async () => {
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(sampleRows);
    localStorage.setItem("watchlistSymbols", "AAA,BBB");

    render(<Watchlist />);

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledWith(["AAA", "BBB"]);

    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("AAA");
    expect(rows[1]).toHaveTextContent("BBB");

    fireEvent.click(screen.getByText("Chg %"));
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("BBB");

    fireEvent.click(screen.getByText("Chg %"));
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("AAA");
  });

  it("shows error message when API fails", async () => {
    (getQuotes as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    localStorage.setItem("watchlistSymbols", "AAA");

    render(<Watchlist />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("allows manual refresh", async () => {
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(sampleRows);
    localStorage.setItem("watchlistSymbols", "AAA");

    render(<Watchlist />);

    await screen.findByText("Alpha");
    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("Refresh"));
    await screen.findByText("Alpha");
    expect(getQuotes).toHaveBeenCalledTimes(2);
  });

  it("auto-refreshes when enabled", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(sampleRows);
    localStorage.setItem("watchlistSymbols", "AAA");

    render(<Watchlist />);

    await act(async () => {
      await Promise.resolve();
    });
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(getQuotes).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it("skips auto-refresh when markets are closed", async () => {
    vi.useFakeTimers();
    const closed = sampleRows.map((r) => ({ ...r, marketState: "CLOSED" }));
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(closed);
    localStorage.setItem("watchlistSymbols", "AAA");

    render(<Watchlist />);

    await act(async () => {
      await Promise.resolve();
    });
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(getQuotes).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });
});

