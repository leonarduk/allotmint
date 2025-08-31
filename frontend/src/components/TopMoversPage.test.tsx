import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { TopMoversPage } from "./TopMoversPage";
import type { MoverRow } from "../types";

vi.mock("../data/watchlists", () => ({
  WATCHLISTS: { "FTSE 100": ["AAA", "BBB"] },
}));

const mockGetTopMovers = vi.fn(() =>
  Promise.resolve({
    gainers: [{ ticker: "AAA", name: "AAA", change_pct: 5 } as MoverRow],
    losers: [{ ticker: "BBB", name: "BBB", change_pct: -2 } as MoverRow],
  }),
);
const mockGetGroupMovers = vi.fn(() =>
  Promise.resolve({

  gainers: [
      {
        ticker: "AAA",
        name: "AAA",
        change_pct: 5,
        market_value_gbp: 100,
      } as MoverRow,
    ],
    losers: [
      {
        ticker: "BBB",
        name: "BBB",
        change_pct: -2,
        market_value_gbp: 50,
      } as MoverRow,
    ],
  }),
);
const mockGetGroupInstruments = vi.fn(() =>
  Promise.resolve([
    {
      ticker: "CCC",
      name: "CCC",
      currency: null,
      units: 0,
      market_value_gbp: 0,
      gain_gbp: 0,
    },
  ]),
);
const mockGetTradingSignals = vi.fn(() =>
  Promise.resolve([
    { ticker: "AAA", action: "buy", reason: "go long" },
  ]),
);

vi.mock("../api", () => ({
  getTopMovers: (
    ...args: Parameters<typeof mockGetTopMovers>
  ) => mockGetTopMovers(...args),
  getGroupInstruments: (
    ...args: Parameters<typeof mockGetGroupInstruments>
  ) => mockGetGroupInstruments(...args),
  getGroupMovers: (
    ...args: Parameters<typeof mockGetGroupMovers>
  ) => mockGetGroupMovers(...args),
  getTradingSignals: (
    ...args: Parameters<typeof mockGetTradingSignals>
  ) => mockGetTradingSignals(...args),
}));

vi.mock("./InstrumentDetail", () => ({
  InstrumentDetail: ({
    ticker,
    onClose,
  }: {
    ticker: string;
    onClose: () => void;
  }) => (
    <div data-testid="detail">
      Detail for {ticker}
      <button onClick={onClose}>x</button>
    </div>
  ),
}));

describe("TopMoversPage", () => {
  it("renders movers and refetches on period change", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

      await waitFor(() =>
        expect(mockGetGroupInstruments).toHaveBeenCalledWith("all"),
      );
      await waitFor(() =>
        expect(mockGetGroupMovers).toHaveBeenCalledWith("all", 1, 10, 0),
      );
    expect((await screen.findAllByText("AAA")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("BBB")).length).toBeGreaterThan(0);

    const selects = screen.getAllByRole("combobox");
    const periodSelect = selects[1];
    fireEvent.change(periodSelect, { target: { value: "1w" } });
      await waitFor(() =>
        expect(mockGetGroupMovers).toHaveBeenLastCalledWith(
          "all",
          7,
          10,
          0,
        ),
      );
  });

  it("fetches watchlist instruments when selecting FTSE 100", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenCalledWith("all", 1, 10, 0),
    );

    const selects = await screen.findAllByRole("combobox");
    const watchlistSelect = selects[0];
    fireEvent.change(watchlistSelect, { target: { value: "FTSE 100" } });

    await waitFor(() =>
      expect(mockGetTopMovers).toHaveBeenLastCalledWith(["AAA", "BBB"], 1),
    );
  });

  it("mounts InstrumentDetail when ticker clicked", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", { name: "AAA" });
    fireEvent.click(button);
    expect(await screen.findByTestId("detail")).toHaveTextContent("AAA");
  });

  it("colors gainers green and losers red", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    const gainerCandidates = await screen.findAllByText("5.00");
    const gainerCell = gainerCandidates.find(
      (el) => (el as HTMLElement).style.color === "green",
    ) as HTMLElement;
    const loserCell = await screen.findByText("-2.00");
    expect(gainerCell).toHaveStyle({ color: "rgb(0, 128, 0)" });
    expect(loserCell).toHaveStyle({ color: "rgb(255, 0, 0)" });
  });

  it("renders trading signals table", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockGetTradingSignals).toHaveBeenCalled());
    expect(await screen.findByText("go long")).toBeInTheDocument();
  });

  it("shows HTTP status when fetch fails", async () => {
    mockGetGroupMovers.mockRejectedValueOnce(
      new Error("HTTP 401 – Unauthorized"),
    );
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/HTTP 401/)).toBeInTheDocument();
  });

  it("falls back to FTSE 100 and prompts login on 401", async () => {
    mockGetGroupMovers.mockRejectedValueOnce(
      new Error("HTTP 401 – Unauthorized"),
    );
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetTopMovers).toHaveBeenCalledWith(["AAA", "BBB"], 1),
    );

    const selects = await screen.findAllByRole("combobox");
    const watchlistSelect = selects[0] as HTMLSelectElement;
    await waitFor(() => expect(watchlistSelect.value).toBe("FTSE 100"));

    expect(
      await screen.findByText(/log in to view portfolio-based movers/i),
    ).toBeInTheDocument();
  });

  it("passes min weight when exclude checkbox checked", async () => {
    render(
      <MemoryRouter>
        <TopMoversPage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenCalledWith("all", 1, 10, 0),
    );

    const checkbox = screen.getByLabelText(/Exclude positions/i);
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenLastCalledWith("all", 1, 10, 0.5),
    );
  });
});
