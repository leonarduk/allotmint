import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { TopMoversSummary } from "./TopMoversSummary";
import type { MoverRow } from "../types";
import moversPlugin from "../plugins/movers";

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

vi.mock("../api", () => ({
  getGroupMovers: (
    ...args: Parameters<typeof mockGetGroupMovers>
  ) => mockGetGroupMovers(...args),
}));

describe("TopMoversSummary", () => {
  it("renders movers and view more link", async () => {
    render(
      <MemoryRouter>
        <TopMoversSummary slug="all" />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetGroupMovers).toHaveBeenCalledWith("all", 1, 5),
    );
    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(await screen.findByText("DDD")).toBeInTheDocument();
    expect(screen.queryByText("FFF")).not.toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view more/i });
    expect(link).toHaveAttribute("href", moversPlugin.path({ group: "all" }));
  });
});
