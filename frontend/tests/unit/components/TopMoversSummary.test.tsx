import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopMoversSummary } from "@/components/TopMoversSummary";
import type { OpportunityEntry } from "@/types";
import moversPlugin from "@/plugins/movers";

const baseEntries: OpportunityEntry[] = [
  { ticker: "AAA", name: "AAA", change_pct: 5, side: "gainers" },
  { ticker: "CCC", name: "CCC", change_pct: 2, side: "gainers" },
  { ticker: "EEE", name: "EEE", change_pct: 1, side: "gainers" },
  { ticker: "BBB", name: "BBB", change_pct: -3, side: "losers" },
  { ticker: "DDD", name: "DDD", change_pct: -4, side: "losers" },
  { ticker: "FFF", name: "FFF", change_pct: -1, side: "losers" },
];

const mockGetOpportunities = vi.fn(() =>
  Promise.resolve({
    entries: baseEntries,
    signals: [],
    context: { source: "group", group: "all", days: 1, anomalies: [] },
  }),
);

vi.mock("@/api", () => ({
  getOpportunities: (
    ...args: Parameters<typeof mockGetOpportunities>
  ) => mockGetOpportunities(...args),
}));

describe("TopMoversSummary", () => {
  beforeEach(() => {
    mockGetOpportunities.mockClear();
  });

  it("renders movers and view more link", async () => {
    render(
      <MemoryRouter>
        <TopMoversSummary slug="all" />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetOpportunities).toHaveBeenCalledWith({
        group: "all",
        days: 1,
        limit: 5,
      }),
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

    await waitFor(() => expect(mockGetOpportunities).not.toHaveBeenCalled());
    expect(screen.getByText(/no group selected/i)).toBeInTheDocument();
  });
});
