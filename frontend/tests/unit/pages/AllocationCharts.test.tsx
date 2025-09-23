import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AllocationCharts from "@/pages/AllocationCharts";
import * as api from "@/api";
import type { GroupPortfolio } from "@/types";

vi.mock("@/api");
const mockGetGroupPortfolio = vi.mocked(api.getGroupPortfolio);

const samplePortfolio: GroupPortfolio = {
  group: "g",
  name: "Group",
  as_of: "2024-01-01",
  members: [],
  total_value_estimate_gbp: 100,
  trades_this_month: 0,
  trades_remaining: 0,
  accounts: [
    {
      account_type: "taxable",
      currency: "GBP",
      value_estimate_gbp: 100,
      owner: "alice",
      holdings: [
        {
          ticker: "AAA",
          name: "Alpha",
          units: 1,
          acquired_date: "2024-01-01",
          market_value_gbp: 100,
          instrument_type: "equity",
          sector: "Tech",
          region: "UK",
        },
      ],
    },
  ],
  members_summary: [],
  subtotals_by_account_type: {},
};

describe("AllocationCharts page", () => {
  it("shows loading indicator while fetching", async () => {
    let resolveFn: (p: GroupPortfolio) => void;
    const promise = new Promise<GroupPortfolio>((resolve) => {
      resolveFn = resolve;
    });
    mockGetGroupPortfolio.mockReturnValueOnce(promise);

    render(<AllocationCharts />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();

    resolveFn!(samplePortfolio);
    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });

  it("displays an error message when API call fails", async () => {
    mockGetGroupPortfolio.mockRejectedValueOnce(new Error("boom"));
    render(<AllocationCharts />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });
});

