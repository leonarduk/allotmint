import { describe, expect, it } from "vitest";
import {
  buildShowingRangeLabel,
  buildTransactionPayload,
  createTransactionFormStateFromTransaction,
  paginateTransactions,
} from "@/components/transactions/helpers";

describe("transaction helpers", () => {
  it("normalises an existing transaction into editable form values", () => {
    expect(
      createTransactionFormStateFromTransaction({
        owner: "alex",
        account: "isa",
        ticker: "vusa",
        amount_minor: 12345,
        shares: 3,
        date: "2024-01-02T10:15:00Z",
        fees: 1.25,
        reason_to_buy: "Long term",
        comments: "Initial position",
      } as any),
    ).toMatchObject({
      owner: "alex",
      account: "isa",
      ticker: "VUSA",
      price: "41.15",
      units: "3",
      date: "2024-01-02",
      fees: "1.25",
      reason: "Long term",
      comments: "Initial position",
    });
  });

  it("builds a validated payload", () => {
    expect(
      buildTransactionPayload({
        owner: "alex",
        account: "isa",
        date: "2024-01-02",
        ticker: " vusa ",
        price: "10.5",
        units: "2",
        fees: "1.2",
        reason: "  Rebalance ",
        comments: "  Optional note  ",
      }),
    ).toEqual({
      ok: true,
      payload: {
        owner: "alex",
        account: "isa",
        date: "2024-01-02",
        ticker: "VUSA",
        price_gbp: 10.5,
        units: 2,
        fees: 1.2,
        reason: "Rebalance",
        comments: "Optional note",
      },
    });
  });

  it("reports validation errors for incomplete forms", () => {
    expect(
      buildTransactionPayload({
        owner: "",
        account: "",
        date: "",
        ticker: "",
        price: "0",
        units: "0",
        fees: "",
        reason: "",
        comments: "",
      }),
    ).toEqual({ ok: false, error: "Please complete all required fields." });
  });

  it("paginates transactions and formats the showing label", () => {
    const transactions = Array.from({ length: 25 }, (_, index) => ({ id: `${index}` }));
    expect(paginateTransactions(transactions as any, 1, 10)).toHaveLength(10);
    expect(buildShowingRangeLabel(25, 1, 10)).toBe("Showing 11-20 of 25");
    expect(buildShowingRangeLabel(0, 0, 10)).toBe("Showing 0 of 0");
  });
});
