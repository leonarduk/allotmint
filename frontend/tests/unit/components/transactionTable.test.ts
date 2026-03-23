import { describe, expect, it } from "vitest";
import {
  buildBulkDeletionOrder,
  formatTransactionAmount,
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
  });
});
