import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

vi.mock("../api", () => ({
  getTopMovers: (...args: unknown[]) => mockGetTopMovers(...args),
  getGroupInstruments: (...args: unknown[]) =>
    mockGetGroupInstruments(...args),
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
    render(<TopMoversPage />);

    await waitFor(() =>
      expect(mockGetTopMovers).toHaveBeenCalledWith(["AAA", "BBB"], 1),
    );
    expect((await screen.findAllByText("AAA")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("BBB")).length).toBeGreaterThan(0);

    const selects = screen.getAllByRole("combobox");
    const periodSelect = selects[1];
    fireEvent.change(periodSelect, { target: { value: "1w" } });
    await waitFor(() => expect(mockGetTopMovers).toHaveBeenLastCalledWith(["AAA", "BBB"], 7));
  });

  it("fetches portfolio instruments when selecting Portfolio", async () => {
    render(<TopMoversPage />);

    const selects = await screen.findAllByRole("combobox");
    const watchlistSelect = selects[0];
    fireEvent.change(watchlistSelect, { target: { value: "Portfolio" } });

    await waitFor(() => expect(mockGetGroupInstruments).toHaveBeenCalledWith("all"));
    await waitFor(() =>
      expect(mockGetTopMovers).toHaveBeenLastCalledWith(["CCC"], 1),
    );
    expect(
      mockGetGroupInstruments.mock.invocationCallOrder[0],
    ).toBeLessThan(mockGetTopMovers.mock.invocationCallOrder.at(-1)!);
  });

  it("mounts InstrumentDetail when ticker clicked", async () => {
    render(<TopMoversPage />);

    const button = await screen.findByRole("button", { name: "AAA" });
    fireEvent.click(button);
    expect(await screen.findByTestId("detail")).toHaveTextContent("AAA");
  });

  it("colors gainers green and losers red", async () => {
    render(<TopMoversPage />);

    const gainerCell = await screen.findByText("5.00");
    const loserCell = await screen.findByText("-2.00");
    expect(gainerCell).toHaveStyle({ color: "rgb(0, 128, 0)" });
    expect(loserCell).toHaveStyle({ color: "rgb(255, 0, 0)" });
  });
});
