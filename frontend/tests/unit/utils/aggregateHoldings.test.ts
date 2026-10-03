import { describe, expect, it } from "vitest";
import {
  aggregateHoldingsByTicker,
  type ScopedHolding,
} from "@/utils/aggregateHoldings";

const lot = (over: Partial<ScopedHolding>): ScopedHolding => ({
  ticker: "AAA",
  name: "Alpha",
  units: 1,
  row_key: "lot",
  ...over,
});

describe("aggregateHoldingsByTicker", () => {
  it("computes gain % from lots with a known cost", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({ cost_basis_gbp: 100, market_value_gbp: 150, gain_gbp: 50 }),
        lot({ cost_basis_gbp: 100, market_value_gbp: 110, gain_gbp: 10 }),
      ],
      "2026-01-01",
    );

    expect(row.gain_gbp).toBe(60);
    expect(row.gain_pct).toBe(30);
  });

  it("returns a null gain, not 0%, when no lot has a known cost (#8471)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({
          cost_basis_gbp: 0,
          effective_cost_basis_gbp: 0,
          market_value_gbp: 100,
          gain_gbp: null,
          gain_pct: null,
        }),
        lot({
          effective_cost_basis_gbp: 40,
          market_value_gbp: 40,
          gain_gbp: 0,
          gain_pct: 0,
          cost_basis_source: "unknown",
        }),
      ],
      "2026-01-01",
    );

    expect(row.market_value_gbp).toBe(140);
    expect(row.gain_gbp).toBeNull();
    expect(row.gain_pct).toBeNull();
  });

  it("leaves unknown-cost lots out of the gain % weighting (#8471)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({
          effective_cost_basis_gbp: 60,
          market_value_gbp: 60,
          gain_gbp: 0,
          cost_basis_source: "unknown",
        }),
        lot({
          cost_basis_gbp: 80,
          market_value_gbp: 100,
          gain_gbp: 20,
          cost_basis_source: "book",
        }),
      ],
      "2026-01-01",
    );

    expect(row.effective_cost_basis_gbp).toBe(140);
    expect(row.gain_gbp).toBe(20);
    expect(row.gain_pct).toBe(25);
    // The known lot's source wins so the table does not hide its real gain.
    expect(row.cost_basis_source).toBe("book");
  });
});
