import { describe, expect, it, vi } from "vitest";
import {
  buildBulkDeletionOrder,
  filterAndSortTransactions,
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
      ),
    ).toEqual({ text: "£490.21", className: "text-positive", title: "Cost basis £4,843.77" });
    expect(
      formatRealisedGain({ ...base, type: "SELL", realised_gain_gbp: -596.54 }).className,
    ).toBe("text-negative");
  });

  it("marks sales with no recorded purchase cost as unknown", () => {
    const cell = formatRealisedGain(
      { ...base, type: "SELL", realised_gain_gbp: null, unmatched_units: 78 },
    );
    expect(cell.text).toBe("Unknown");
    expect(cell.title).toContain("78");
  });

  it("marks sales with no recorded proceeds as unknown", () => {
    const cell = formatRealisedGain(
      { ...base, type: "SELL", realised_gain_gbp: null, cost_basis_gbp: 100, proceeds_gbp: null },
    );
    expect(cell.text).toBe("Unknown");
    expect(cell.title).toContain("proceeds");
  });

  it("leaves non-disposal rows blank", () => {
    expect(formatRealisedGain({ ...base, type: "BUY" }).text).toBe("");
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

describe("filterAndSortTransactions", () => {
  const tx = (id: string, type: string, date: string | null) => ({
    id,
    owner: "alex",
    account: "isa",
    type,
    date,
  });
  const rows = [
    tx("a", "BUY", "2024-01-01"),
    tx("b", "SELL", "2024-03-01"),
    tx("c", "DIVIDEND", "2024-02-01"),
    tx("d", "purchase", "2024-04-01"),
    tx("e", "SALE", null),
  ];

  it("returns every row newest first, undated last", () => {
    expect(filterAndSortTransactions(rows, "").map((r) => r.id)).toEqual([
      "d",
      "b",
      "c",
      "a",
      "e",
    ]);
  });

  it("keeps only buys (including PURCHASE) for the Buy filter", () => {
    expect(filterAndSortTransactions(rows, "BUY").map((r) => r.id)).toEqual(["d", "a"]);
  });

  it("keeps only sells (including SALE) for the Sell filter", () => {
    expect(filterAndSortTransactions(rows, "SELL").map((r) => r.id)).toEqual(["b", "e"]);
  });

  it("does not mutate the input array", () => {
    const input = [...rows];
    filterAndSortTransactions(input, "");
    expect(input.map((r) => r.id)).toEqual(["a", "b", "c", "d", "e"]);
  });
});
