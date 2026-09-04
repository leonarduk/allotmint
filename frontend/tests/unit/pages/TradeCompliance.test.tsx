import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetTransactionsWithCompliance = vi.hoisted(() => vi.fn());
const mockRequestApproval = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getOwners: mockGetOwners,
  getTransactionsWithCompliance: mockGetTransactionsWithCompliance,
  requestApproval: mockRequestApproval,
}));

import TradeCompliance from "@/pages/TradeCompliance";
import type { OwnerSummary, TransactionWithCompliance } from "@/types";

const owners: OwnerSummary[] = [
  { owner: "alice", accounts: [] },
  { owner: "bob", accounts: [] },
];

function renderAtOwner(owner?: string) {
  const initialEntry = owner ? `/trade-compliance/${owner}` : "/trade-compliance";
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/trade-compliance" element={<TradeCompliance />} />
        <Route path="/trade-compliance/:owner" element={<TradeCompliance />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TradeCompliance page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetOwners.mockResolvedValue(owners);
    mockGetTransactionsWithCompliance.mockResolvedValue({ transactions: [] });
    mockRequestApproval.mockResolvedValue({ requests: [] });
  });

  it("loads owners and renders them via OwnerSelector", async () => {
    renderAtOwner();

    await waitFor(() => expect(mockGetOwners).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("option", { name: "alice" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "bob" })).toBeInTheDocument();
  });

  it("loads trades for the selected owner and renders the trades table", async () => {
    const trades: TransactionWithCompliance[] = [
      {
        owner: "alice",
        account: "isa",
        date: "2024-01-05",
        ticker: "AAA",
        type: "buy",
        warnings: [],
      },
    ];
    mockGetTransactionsWithCompliance.mockResolvedValue({ transactions: trades });

    renderAtOwner("alice");

    await waitFor(() =>
      expect(mockGetTransactionsWithCompliance).toHaveBeenCalledWith("alice"),
    );
    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(screen.getByText("2024-01-05")).toBeInTheDocument();
  });

  it("shows the Request Approval button only for trades with a without-approval warning", async () => {
    const trades: TransactionWithCompliance[] = [
      {
        owner: "alice",
        account: "isa",
        date: "2024-01-05",
        ticker: "AAA",
        type: "buy",
        warnings: ["Traded without approval"],
      },
      {
        owner: "alice",
        account: "isa",
        date: "2024-01-06",
        ticker: "BBB",
        type: "sell",
        warnings: ["Some other warning"],
      },
    ];
    mockGetTransactionsWithCompliance.mockResolvedValue({ transactions: trades });

    renderAtOwner("alice");

    await screen.findByText("AAA");
    expect(screen.getByText("BBB")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Request Approval" }),
    ).toBeInTheDocument();
    // Only one row qualifies for the approval button.
    expect(screen.getAllByRole("button", { name: "Request Approval" })).toHaveLength(1);
  });

  it("calls requestApproval with the owner and ticker, then flips the button to Requested/disabled", async () => {
    const trades: TransactionWithCompliance[] = [
      {
        owner: "alice",
        account: "isa",
        date: "2024-01-05",
        ticker: "AAA",
        type: "buy",
        warnings: ["Traded without approval"],
      },
    ];
    mockGetTransactionsWithCompliance.mockResolvedValue({ transactions: trades });
    mockRequestApproval.mockResolvedValue({
      requests: [{ ticker: "AAA", requested_on: "2024-01-07" }],
    });

    renderAtOwner("alice");

    const button = await screen.findByRole("button", { name: "Request Approval" });
    fireEvent.click(button);

    await waitFor(() => expect(mockRequestApproval).toHaveBeenCalledWith("alice", "AAA"));

    const requestedButton = await screen.findByRole("button", { name: "Requested" });
    expect(requestedButton).toBeDisabled();
  });

  it("renders an error message and clears the trades list when loading transactions fails", async () => {
    mockGetTransactionsWithCompliance.mockResolvedValueOnce({
      transactions: [
        {
          owner: "alice",
          account: "isa",
          date: "2024-01-05",
          ticker: "AAA",
          type: "buy",
          warnings: [],
        },
      ],
    });

    renderAtOwner("alice");
    await screen.findByText("AAA");

    mockGetTransactionsWithCompliance.mockRejectedValueOnce(new Error("boom"));

    fireEvent.change(screen.getByLabelText(/owner/i), { target: { value: "bob" } });

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByText("AAA")).not.toBeInTheDocument();
  });
});
