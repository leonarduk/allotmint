import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import i18n from "@/i18n";
import { TransactionsPage } from "@/components/TransactionsPage";

vi.mock("@/api", () => ({
  getTransactions: vi.fn(() =>
    Promise.resolve([
      {
        owner: "alex",
        account: "isa",
        ticker: "PFE",
        type: "BUY",
        amount_minor: 10000,
        currency: "GBP",
        shares: 5,
        date: "2024-01-01",
      },
    ])
  ),
}));

describe("TransactionsPage", () => {
  it("displays instrument ticker", async () => {
    render(<TransactionsPage owners={[{ owner: "alex", accounts: ["isa"] }]} />);
    expect(await screen.findByText("PFE")).toBeInTheDocument();
  });
});

