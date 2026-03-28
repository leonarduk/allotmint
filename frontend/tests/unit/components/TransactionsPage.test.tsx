import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TransactionsPage } from "@/components/TransactionsPage";

vi.mock("@/api", () => ({
  getTransactions: vi.fn(() =>
    Promise.resolve([
      {
        id: "tx-1",
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
    render(
      <TransactionsPage
        owners={[{ owner: "alex", full_name: "Alex Example", accounts: ["isa"] }]}
      />,
    );
    expect(await screen.findByText("PFE")).toBeInTheDocument();
    expect((await screen.findAllByText("Alex Example")).at(-1)).toBeInTheDocument();
  });

  it("locks owner and account filters while editing", async () => {
    render(
      <TransactionsPage
        owners={[{ owner: "alex", full_name: "Alex Example", accounts: ["isa"] }]}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText(/owner/i)).toBeDisabled();
    expect(screen.getByLabelText(/account/i)).toBeDisabled();
    expect(
      screen.getByText(/owner and account filters are locked until you save or cancel/i),
    ).toBeInTheDocument();
  });
});
