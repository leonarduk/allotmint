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
  it("takes sell_block_reason from the oldest lot (#10812)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({
          acquired_date: "2025-12-20",
          sell_eligible: false,
          sell_block_reason: "hold_period",
        }),
        lot({
          acquired_date: "2024-05-01",
          sell_eligible: false,
          sell_block_reason: "needs_approval",
        }),
      ],
      "2026-01-01",
    );

    expect(row.sell_eligible).toBe(false);
    expect(row.sell_block_reason).toBe("needs_approval");
  });

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

  it("marks the combined row as an estimate when any counted lot's cost is one (#10095)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({ cost_basis_gbp: 80, market_value_gbp: 100, gain_gbp: 20, cost_basis_source: "book" }),
        lot({
          cost_basis_gbp: 20,
          market_value_gbp: 25,
          gain_gbp: 5,
          cost_basis_source: "estimate",
          cost_basis_estimate_date: "2026-10-01",
        }),
      ],
      "2026-11-01",
    );

    expect(row.gain_gbp).toBe(25);
    expect(row.cost_basis_source).toBe("estimate");
    expect(row.cost_basis_estimate_date).toBe("2026-10-01");
  });

  it("still marks the row an estimate when the estimated lot has no gain of its own (#11395)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({ cost_basis_gbp: 80, market_value_gbp: 100, gain_gbp: 20, cost_basis_source: "book" }),
        lot({
          cost_basis_gbp: 20,
          gain_gbp: null,
          cost_basis_source: "estimate",
          cost_basis_estimate_date: "2026-10-01",
        }),
      ],
      "2026-11-01",
    );

    // Only the book lot's gain is summed, but the estimated cost is in the total.
    expect(row.gain_gbp).toBe(20);
    expect(row.cost_basis_gbp).toBe(100);
    expect(row.cost_basis_source).toBe("estimate");
    expect(row.cost_basis_estimate_date).toBe("2026-10-01");
  });

  it("keeps the estimate tag and its gain beside an unreliable lot (#11395)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({ effective_cost_basis_gbp: 60, market_value_gbp: 60, gain_gbp: 0, cost_basis_source: "unknown" }),
        lot({ cost_basis_gbp: 20, market_value_gbp: 25, gain_gbp: 5, cost_basis_source: "estimate" }),
      ],
      "2026-11-01",
    );

    // An estimate is not unreliable, so its gain is still counted, and flagged.
    expect(row.gain_gbp).toBe(5);
    expect(row.cost_basis_source).toBe("estimate");
  });

  it("tags an estimate row with no counted gain as an estimate (#11395)", () => {
    const [row] = aggregateHoldingsByTicker(
      [
        lot({ cost_basis_gbp: 20, gain_gbp: null, cost_basis_source: "estimate" }),
        lot({ effective_cost_basis_gbp: 30, gain_gbp: 0, cost_basis_source: "unknown" }),
      ],
      "2026-11-01",
    );

    expect(row.gain_gbp).toBeNull();
    expect(row.cost_basis_source).toBe("estimate");
  });
});
