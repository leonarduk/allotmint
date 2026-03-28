import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TransactionsPage } from "@/components/TransactionsPage";

const { getTransactionsMock, createTransactionMock } = vi.hoisted(() => ({
  getTransactionsMock: vi.fn(() =>
    Promise.resolve([
      {
        id: "tx-1",
        id: "alex:isa:0",
        owner: "alex",
        account: "isa",
        ticker: "PFE",
        type: "BUY",
        amount_minor: 10000,
        currency: "GBP",
        shares: 5,
        date: "2024-01-01",
        reason: "Initial",
      },
      {
        id: "sam:sipp:1",
        owner: "sam",
        account: "sipp",
        ticker: "MSFT",
        type: "BUY",
        amount_minor: 20000,
        currency: "GBP",
        units: 10,
        date: "2024-01-02",
        reason: "Growth",
      },
    ]),
  ),
  createTransactionMock: vi.fn(() => Promise.resolve({})),
}));

vi.mock("@/api", () => ({
  getTransactions: getTransactionsMock,
  createTransaction: createTransactionMock,
  updateTransaction: vi.fn(() => Promise.resolve({})),
  deleteTransaction: vi.fn(() => Promise.resolve({})),
}));

describe("TransactionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays instrument ticker", async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: "alex", full_name: "Alex Example", accounts: ["isa"] },
          { owner: "sam", full_name: "Sam Example", accounts: ["sipp"] },
        ]}
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
  it("syncs filter owner/account when editing and reflects it in the editor context", async () => {
    render(
      <TransactionsPage
        owners={[
          { owner: "alex", full_name: "Alex Example", accounts: ["isa"] },
          { owner: "sam", full_name: "Sam Example", accounts: ["sipp"] },
        ]}
      />,
    );

    await screen.findByText("MSFT");
    const [ownerFilter, accountFilter] = screen.getAllByRole("combobox");

    expect(ownerFilter).toHaveValue("");
    expect(accountFilter).toHaveValue("");

    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]!);

    expect(ownerFilter).toHaveValue("sam");
    expect(accountFilter).toHaveValue("sipp");
    expect(screen.getByText("sam / sipp")).toBeInTheDocument();
  });

  it("guards validation when submitting without filter owner/account context", async () => {
    render(<TransactionsPage owners={[{ owner: "alex", full_name: "Alex Example", accounts: ["isa"] }]} />);
    await screen.findByText("PFE");

    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2024-03-01" } });
    fireEvent.change(screen.getByLabelText("Ticker"), { target: { value: "VUSA" } });
    fireEvent.change(screen.getByLabelText("Price (GBP)"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Units"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "test reason" } });

    fireEvent.submit(screen.getByRole("button", { name: "Add transaction" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Select an owner and account in the filters before saving.")).toBeInTheDocument();
    });
    expect(createTransactionMock).not.toHaveBeenCalled();
  });
});
