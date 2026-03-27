import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AllocationCharts from "@/pages/AllocationCharts";
import * as api from "@/api";
import type { GroupPortfolio } from "@/types";

vi.mock("@/api");
const mockGetGroupPortfolio = vi.mocked(api.getGroupPortfolio);

const samplePortfolio: GroupPortfolio = {
  slug: "g",
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

  it("ignores non-positive values without crashing", async () => {
    mockGetGroupPortfolio.mockResolvedValueOnce({
      ...samplePortfolio,
      accounts: [
        {
          ...samplePortfolio.accounts[0],
          holdings: [
            {
              ...samplePortfolio.accounts[0].holdings[0],
              ticker: "NEG",
              market_value_gbp: -20,
              sector: "Utilities",
            },
            {
              ...samplePortfolio.accounts[0].holdings[0],
              ticker: "BAD",
              market_value_gbp: Number.NaN as unknown as number,
              sector: "Finance",
            },
            {
              ...samplePortfolio.accounts[0].holdings[0],
              ticker: "OK",
              market_value_gbp: 100,
              sector: "Tech",
            },
          ],
        },
      ],
    });

    render(<AllocationCharts />);

    expect(await screen.findByText(/Instrument Types/)).toBeInTheDocument();
    expect(screen.queryByText(/boom/i)).not.toBeInTheDocument();
  });
});
