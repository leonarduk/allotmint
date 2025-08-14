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

vi.mock("../api", () => ({
  getTopMovers: (...args: any[]) => mockGetTopMovers(...args),
  getGroupMovers: vi.fn(),
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
});
