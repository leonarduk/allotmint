import { render, screen, fireEvent } from "@testing-library/react";
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
    time: "2024-01-01T00:00:00Z",
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
    time: "2024-01-01T01:00:00Z",
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
});

