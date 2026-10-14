import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  createTransactionFormValues,
  maxTransactionDate,
} from "@/components/transactions/transactionForm";

const BASE_VALUES = {
  type: "BUY",
  date: "2024-02-01",
  ticker: "VUSA",
  price: "12.50",
  units: "3",
  fees: "",
  comments: "",
  reason: "rebalance",
};

describe("transactionForm helpers", () => {
  it("creates editable form values from a transaction", () => {
    expect(
      createTransactionFormValues({
        owner: "alex",
        account: "isa",
        ticker: "vusa",
        amount_minor: 1050,
        // Portfolio Performance fixed-point: 2 units x 10^8 (#10203).
        shares: 200_000_000,
        fees: 1.5,
        comments: "note",
        reason_to_buy: "long term",
        date: "2024-02-01T10:00:00Z",
      }),
    ).toEqual({
      type: "",
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
      shares: 300_000_000,
      date: "2024-02-01T00:00:00Z",
    });
    expect(result.price).toBe("3.33");
  });

  it("builds a valid transaction payload", () => {
    expect(
      buildTransactionPayload({
        type: "BUY",
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
        type: "BUY",
        fees: 1.25,
        comments: "add more",
        reason: "rebalance",
      },
    });
  });

  it("returns a validation error for invalid fees", () => {
    expect(
      buildTransactionPayload({
        type: "BUY",
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
        type: "BUY",
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
        type: "BUY",
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
  it("keeps SELL when editing a sale", () => {
    const values = createTransactionFormValues({
      owner: "alex",
      account: "isa",
      type: "sell",
      date: "2024-02-01",
    });
    expect(values.type).toBe("SELL");
  });

  it("keeps a non-trade type so the form can leave it unchanged", () => {
    const values = createTransactionFormValues({
      owner: "alex",
      account: "isa",
      type: "DIVIDEND",
      date: "2024-02-01",
    });
    expect(values.type).toBe("DIVIDEND");
  });

  it("leaves an untyped legacy entry untyped so saving it does not start counting it", () => {
    const values = createTransactionFormValues({
      owner: "alex",
      account: "isa",
      ticker: "VUSA",
      price_gbp: 10,
      units: 2,
      reason: "legacy",
      date: "2024-02-01",
    });
    expect(values.type).toBe("");
    const result = buildTransactionPayload(values, "alex", "isa");
    expect(result.error).toBeNull();
    expect(result.payload).not.toHaveProperty("type");
  });

  it("includes SELL in the payload", () => {
    const result = buildTransactionPayload(
      { ...BASE_VALUES, type: "SELL" },
      "alex",
      "isa",
    );
    expect(result.payload?.type).toBe("SELL");
  });

  it("omits a non-trade type from the payload so the stored type is kept", () => {
    const result = buildTransactionPayload(
      { ...BASE_VALUES, type: "DIVIDEND" },
      "alex",
      "isa",
    );
    expect(result.error).toBeNull();
    expect(result.payload).not.toHaveProperty("type");
  });

  describe("future dates (#10898)", () => {
    // Local noon, so the local calendar date is the same in every timezone.
    const NOW = new Date(2026, 9, 14, 12, 0, 0);

    it("allows up to tomorrow in the browser's timezone", () => {
      expect(maxTransactionDate(NOW)).toBe("2026-10-15");
      expect(maxTransactionDate(new Date(2026, 11, 31, 12))).toBe("2027-01-01");
    });

    it("rejects a date after tomorrow", () => {
      expect(
        buildTransactionPayload({ ...BASE_VALUES, date: "2027-01-01" }, "alex", "isa", NOW),
      ).toEqual({ payload: null, error: "Date cannot be in the future." });
    });

    it("accepts today and tomorrow", () => {
      for (const date of ["2026-10-14", "2026-10-15"]) {
        const result = buildTransactionPayload({ ...BASE_VALUES, date }, "alex", "isa", NOW);
        expect(result.error).toBeNull();
        expect(result.payload?.date).toBe(date);
      }
    });
  });
});
