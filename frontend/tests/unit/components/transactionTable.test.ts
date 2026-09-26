import { describe, expect, it, vi } from "vitest";
import {
  buildBulkDeletionOrder,
  formatRealisedGain,
  formatTransactionAmount,
  summariseTransactions,
} from "@/components/transactions/transactionTable";

describe("transactionTable helpers", () => {
  it("orders grouped deletions from highest index to lowest", () => {
    expect(
      buildBulkDeletionOrder([
        "alex:isa:1",
        "alex:isa:4",
        "alex:sipp:2",
        "legacy-id",
      ]),
    ).toEqual(["alex:isa:4", "alex:isa:1", "alex:sipp:2", "legacy-id"]);
  });

  it("treats IDs that do not match owner:account:index format as fallback (unordered)", () => {
    // UUIDs and other opaque IDs must not silently corrupt deletion order;
    // they fall through to the fallback list and are deleted in input order.
    const uuids = [
      "550e8400-e29b-41d4-a716-446655440000",
      "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    ];
    expect(buildBulkDeletionOrder(uuids)).toEqual(uuids);
  });

  it("formats amount using explicit currency before derived price", () => {
    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          amount_minor: 12345,
          currency: "USD",
          price_gbp: 50,
          units: 10,
        },
        "GBP",
      ),
    ).toBe("$123.45");

    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          price_gbp: 12.5,
          units: 3,
        },
        "GBP",
      ),
    ).toBe("£37.50");

    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          price_gbp: 8,
          shares: 2.5,
        },
        "GBP",
      ),
    ).toBe("£20.00");
  });

  it("uses units precedence and warns when units and shares both exist", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          price_gbp: 10,
          units: 3,
          shares: 9,
        },
        "GBP",
      ),
    ).toBe("£30.00");
    expect(warnSpy).toHaveBeenCalledOnce();
    warnSpy.mockRestore();
  });

  it("returns blank when price is missing or non-numeric", () => {
    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          units: 3,
        },
        "GBP",
      ),
    ).toBe("");

    expect(
      formatTransactionAmount(
        {
          owner: "alex",
          account: "isa",
          price_gbp: Number.NaN,
          units: 3,
        },
        "GBP",
      ),
    ).toBe("");
  });
});

describe("realised gain helpers", () => {
  const base = { owner: "steve", account: "isa" };

  it("formats a known gain with sign styling and cost basis tooltip", () => {
    expect(
      formatRealisedGain(
        { ...base, type: "SELL", realised_gain_gbp: 490.21, cost_basis_gbp: 4843.77 },
        "GBP",
      ),
    ).toEqual({ text: "£490.21", className: "text-positive", title: "Cost basis £4,843.77" });
    expect(
      formatRealisedGain({ ...base, type: "SELL", realised_gain_gbp: -596.54 }, "GBP").className,
    ).toBe("text-negative");
  });

  it("marks sales with no recorded purchase cost as unknown", () => {
    const cell = formatRealisedGain(
      { ...base, type: "SELL", realised_gain_gbp: null, unmatched_units: 78 },
      "GBP",
    );
    expect(cell.text).toBe("Unknown");
    expect(cell.title).toContain("78");
  });

  it("leaves non-disposal rows blank", () => {
    expect(formatRealisedGain({ ...base, type: "BUY" }, "GBP").text).toBe("");
  });

  it("summarises realised gain, income and net fees", () => {
    expect(
      summariseTransactions([
        { ...base, type: "SELL", realised_gain_gbp: 100 },
        { ...base, type: "SELL", realised_gain_gbp: -40 },
        { ...base, type: "SELL", realised_gain_gbp: null, unmatched_units: 5 },
        { ...base, type: "DIVIDEND", amount_minor: 1000 },
        { ...base, type: "INTEREST", amount_minor: 250 },
        { ...base, type: "FEES", amount_minor: 500 },
        { ...base, type: "FEES_REFUND", amount_minor: 200 },
      ]),
    ).toEqual({ realisedGain: 60, sellsWithUnknownGain: 1, income: 12.5, fees: 3 });
  });
});
