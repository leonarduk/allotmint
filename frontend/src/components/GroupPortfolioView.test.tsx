import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { GroupPortfolioView } from "./GroupPortfolioView";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GroupPortfolioView", () => {
  it("shows per-owner totals with percentages", async () => {
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              day_change_gbp: 5,
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 150,
              market_value_gbp: 200,
              day_change_gbp: -10,
            },
          ],
        },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockPortfolio,
    } as unknown as Response);

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getByText("alice"));

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("25.00%"))
      .toBeInTheDocument();
    expect(screen.getByText("-4.76%"))
      .toBeInTheDocument();
  });

  it("renders instrument type pie chart", async () => {
    const mockPortfolio = {
      name: "All owners combined",
      accounts: [
        {
          owner: "alice",
          account_type: "isa",
          value_estimate_gbp: 100,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 80,
              market_value_gbp: 100,
              instrument_type: "equity",
            },
          ],
        },
        {
          owner: "bob",
          account_type: "isa",
          value_estimate_gbp: 200,
          holdings: [
            {
              units: 1,
              cost_basis_gbp: 200,
              market_value_gbp: 200,
              instrument_type: "cash",
            },
          ],
        },
      ],
    };

    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockPortfolio,
    } as unknown as Response);

    render(<GroupPortfolioView slug="all" />);

    await waitFor(() => screen.getByText("Equity"));

    expect(screen.getByText("Equity")).toBeInTheDocument();
    expect(screen.getByText("Cash")).toBeInTheDocument();
  });
});
