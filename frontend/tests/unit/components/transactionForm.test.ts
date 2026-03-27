import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  createTransactionFormValues,
} from "@/components/transactions/transactionForm";

describe("transactionForm helpers", () => {
  it("creates editable form values from a transaction", () => {
    expect(
      createTransactionFormValues({
        owner: "alex",
        account: "isa",
        ticker: "vusa",
        amount_minor: 1050,
        shares: 2,
        fees: 1.5,
        comments: "note",
        reason_to_buy: "long term",
        date: "2024-02-01T10:00:00Z",
      }),
    ).toEqual({
      ticker: "VUSA",
      price: "5.25",
      units: "2",
      fees: "1.5",
      comments: "note",
      reason: "long term",
      date: "2024-02-01",
    });
  });

  it("rounds derived price to 2dp when amount_minor / units is a repeating decimal", () => {
    // 1000 minor / 100 / 3 = 3.3333... — must not be stored as a long float
    const result = createTransactionFormValues({
      owner: "alex",
      account: "isa",
      amount_minor: 1000,
      shares: 3,
      date: "2024-02-01T00:00:00Z",
    });
    expect(result.price).toBe("3.33");
  });

  it("builds a valid transaction payload", () => {
    expect(
      buildTransactionPayload({
        date: "2024-02-01",
        ticker: " vusa ",
        price: "12.50",
        units: "3",
        fees: "1.25",
        comments: " add more ",
        reason: " rebalance ",
      }, "alex", "isa"),
    ).toEqual({
      error: null,
      payload: {
        owner: "alex",
        account: "isa",
        date: "2024-02-01",
        ticker: "VUSA",
        price_gbp: 12.5,
        units: 3,
        fees: 1.25,
        comments: "add more",
        reason: "rebalance",
      },
    });
  });

  it("returns a validation error for invalid fees", () => {
    expect(
      buildTransactionPayload({
        date: "2024-02-01",
        ticker: "VUSA",
        price: "12.50",
        units: "3",
        fees: "abc",
        comments: "",
        reason: "rebalance",
      }, "alex", "isa"),
    ).toEqual({
      payload: null,
      error: "Enter a valid fee or leave it blank.",
    });
  });

  it("rejects partially-numeric fee strings like '1.5abc'", () => {
    // parseFloat("1.5abc") === 1.5 would silently pass; Number("1.5abc") === NaN
    // correctly rejects it.
    expect(
      buildTransactionPayload({
        date: "2024-02-01",
        ticker: "VUSA",
        price: "12.50",
        units: "3",
        fees: "1.5abc",
        comments: "",
        reason: "rebalance",
      }, "alex", "isa"),
    ).toEqual({
      payload: null,
      error: "Enter a valid fee or leave it blank.",
    });
  });

  it("returns a validation error for negative fees", () => {
    expect(
      buildTransactionPayload({
        date: "2024-02-01",
        ticker: "VUSA",
        price: "12.50",
        units: "3",
        fees: "-1",
        comments: "",
        reason: "rebalance",
      }, "alex", "isa"),
    ).toEqual({
      payload: null,
      error: "Fees cannot be negative.",
    });
  });
});
