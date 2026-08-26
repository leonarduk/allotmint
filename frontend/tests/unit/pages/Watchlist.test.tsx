import { render, screen, fireEvent } from "@testing-library/react";
import { act } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api", () => ({
  getQuotes: vi.fn(),
}));

import { Watchlist } from "@/pages/Watchlist";
import { getQuotes } from "@/api";
import type { QuoteRow } from "@/types";

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

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await vi.advanceTimersByTimeAsync(0);
}

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

    const { unmount } = render(<Watchlist />);

    expect(await screen.findByText("boom")).toBeInTheDocument();

    unmount();
  });

  it("allows manual refresh and auto-refresh", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");
    const { unmount } = render(<Watchlist />);

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getAllByRole("button", { name: /refresh/i })[0],
    );
    await act(async () => Promise.resolve());

    expect(getQuotes).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(3);

    unmount();
    vi.useRealTimers();
  });

  it("auto-refreshes when enabled", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = render(<Watchlist />);

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
    unmount();
  });

  it("allows toggling refresh frequency", async () => {
    vi.useFakeTimers();
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([sampleRows[0]]);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = render(<Watchlist />);

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();

    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getAllByLabelText(/Auto-refresh/)[0], {
      target: { value: "0" },
    });

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getAllByLabelText(/Auto-refresh/)[0], {
      target: { value: "60000" },
    });

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(2);

    unmount();
    vi.useRealTimers();
  });

  it("skips auto-refresh when markets are closed", async () => {
    vi.useFakeTimers();
    const closed = [{ ...sampleRows[0], marketState: "CLOSED" }];
    (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue(closed);
    localStorage.setItem("watchlistSymbols", "AAA");

    const { unmount } = render(<Watchlist />);

    await flushPromises();
    expect(screen.getAllByText("Alpha")[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(10000);
    await flushPromises();
    expect(screen.getAllByText(/markets/i)[0]).toBeInTheDocument();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(30000);
    await flushPromises();
    expect(getQuotes).toHaveBeenCalledTimes(1);

    unmount();
    vi.useRealTimers();
  });

  describe("symbol chip editor (#7110)", () => {
    beforeEach(() => {
      (getQuotes as ReturnType<typeof vi.fn>).mockResolvedValue([]);
      localStorage.setItem("watchlistSymbols", "AAA,BBB");
    });

    it("gives the add field an accessible name and renders a chip per symbol", async () => {
      render(<Watchlist />);

      expect(
        await screen.findByLabelText("Watched tickers"),
      ).toBeInTheDocument();
      expect(screen.getByLabelText("Remove AAA")).toBeInTheDocument();
      expect(screen.getByLabelText("Remove BBB")).toBeInTheDocument();
    });

    it("adds a typed ticker on Enter, uppercased, and clears the field", async () => {
      render(<Watchlist />);

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: " ccc " } });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(input.value).toBe("");
      expect(screen.getByLabelText("Remove CCC")).toBeInTheDocument();
      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB,CCC");
    });

    it("removes a symbol via its chip button", async () => {
      render(<Watchlist />);

      fireEvent.click(await screen.findByLabelText("Remove AAA"));

      expect(screen.queryByLabelText("Remove AAA")).not.toBeInTheDocument();
      expect(localStorage.getItem("watchlistSymbols")).toBe("BBB");
    });

    it("ignores a duplicate regardless of case", async () => {
      render(<Watchlist />);

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "aaa" } });
      fireEvent.click(screen.getByRole("button", { name: "Add" }));

      expect(input.value).toBe("");
      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB");
    });

    it("splits a pasted comma-separated list instead of storing it as one symbol", async () => {
      render(<Watchlist />);

      const input = (await screen.findByLabelText(
        "Watched tickers",
      )) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "CCC, DDD ,AAA" } });
      fireEvent.keyDown(input, { key: "Enter" });

      expect(localStorage.getItem("watchlistSymbols")).toBe("AAA,BBB,CCC,DDD");
      expect(screen.getByLabelText("Remove CCC")).toBeInTheDocument();
      expect(screen.getByLabelText("Remove DDD")).toBeInTheDocument();
    });
  });
});
