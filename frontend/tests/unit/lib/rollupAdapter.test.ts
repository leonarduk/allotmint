import { describe, expect, it } from "vitest";
import {
  toRollupRows,
  toScopedHoldingRows,
} from "@/lib/rollupAdapter";
import type { Account, InstrumentSummary } from "@/types";

const accounts: Account[] = [
  {
    owner: "alice",
    account_type: "ISA",
    currency: "GBP",
    value_estimate_gbp: 180,
    holdings: [
      {
        ticker: "AAA",
        name: "Alpha",
        units: 2,
        cost_basis_gbp: 100,
        market_value_gbp: 120,
        gain_gbp: 20,
        acquired_date: "2025-01-01",
        days_held: 100,
        sell_eligible: true,
        days_until_eligible: 0,
        next_eligible_sell_date: "2025-01-01",
      },
      {
        ticker: "BBB",
        name: "Beta",
        units: 3,
        cost_basis_gbp: 50,
        market_value_gbp: 60,
        gain_gbp: 10,
      },
    ],
  },
  {
    owner: "bob",
    account_type: "SIPP",
    currency: "GBP",
    value_estimate_gbp: 180,
    holdings: [
      {
        ticker: "AAA",
        name: "Alpha",
        units: 1,
        cost_basis_gbp: 50,
        market_value_gbp: 180,
        gain_gbp: 130,
        sell_eligible: false,
      },
    ],
  },
];

describe("toScopedHoldingRows", () => {
  it("flattens account holdings and annotates their provenance", () => {
    const rows = toScopedHoldingRows(accounts);

    expect(rows).toHaveLength(3);
    expect(rows[0]).toMatchObject({
      ticker: "AAA",
      owner: "alice",
      source_account: "ISA",
      row_key: "alice:ISA:AAA:0",
    });
    expect(rows[2]).toMatchObject({
      ticker: "AAA",
      owner: "bob",
      source_account: "SIPP",
      row_key: "bob:SIPP:AAA:2",
    });
    expect(new Set(rows.map(({ row_key }) => row_key)).size).toBe(rows.length);
  });
});

describe("toRollupRows", () => {
  it("aggregates lots, recomputes percentages, and retains provenance", () => {
    const rows = toRollupRows(toScopedHoldingRows(accounts));

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({
      ticker: "AAA",
      name: "Alpha",
      units: 3,
      cost_basis_gbp: 150,
      effective_cost_basis_gbp: 150,
      market_value_gbp: 300,
      gain_gbp: 150,
      gain_pct: 100,
      weight_pct: 300 / 360 * 100,
      lot_count: 2,
      owners: ["alice", "bob"],
      accounts: ["ISA", "SIPP"],
    });
  });

  it("uses the effective cost basis when a position has no booked cost", () => {
    const derivedCostAccounts: Account[] = [
      {
        owner: "alice",
        account_type: "ISA",
        currency: "GBP",
        value_estimate_gbp: 100,
        holdings: [
          {
            ticker: "CCC",
            name: "Gamma",
            units: 10,
            cost_basis_gbp: 0,
            effective_cost_basis_gbp: 80,
            market_value_gbp: 100,
            gain_gbp: 20,
          },
        ],
      },
    ];

    const [row] = toRollupRows(toScopedHoldingRows(derivedCostAccounts));

    // Regression: the rollup must not collapse to £0.00 cost / 0% gain when
    // the position's cost is derived rather than booked.
    expect(row).toMatchObject({
      ticker: "CCC",
      cost_basis_gbp: 0,
      effective_cost_basis_gbp: 80,
      gain_gbp: 20,
      gain_pct: 25,
    });
  });

  it("rolls up a mix of booked and derived lots to the full effective cost", () => {
    const mixedAccounts: Account[] = [
      {
        owner: "alice",
        account_type: "ISA",
        currency: "GBP",
        value_estimate_gbp: 100,
        holdings: [
          {
            ticker: "DDD",
            name: "Delta",
            units: 1,
            cost_basis_gbp: 30,
            effective_cost_basis_gbp: 30,
            market_value_gbp: 40,
            gain_gbp: 10,
          },
          {
            ticker: "DDD",
            name: "Delta",
            units: 1,
            effective_cost_basis_gbp: 50,
            market_value_gbp: 60,
            gain_gbp: 10,
          },
        ],
      },
    ];

    const [row] = toRollupRows(toScopedHoldingRows(mixedAccounts));

    expect(row).toMatchObject({
      ticker: "DDD",
      cost_basis_gbp: 30,
      effective_cost_basis_gbp: 80,
      gain_gbp: 20,
      gain_pct: 25,
    });
  });

  it("derives acquisition/eligibility fields from the oldest dated lot", () => {
    // AAA has two lots: alice's, acquired 2025-01-01, and bob's, with no
    // acquired_date at all. The rollup must use alice's lot (the only one
    // with a usable date) rather than blanking the columns out entirely.
    const [row] = toRollupRows(
      toScopedHoldingRows(accounts),
      [],
      "2025-04-11",
    );

    expect(row).toMatchObject({
      ticker: "AAA",
      acquired_date: "2025-01-01",
      days_held: 100,
      sell_eligible: true,
      days_until_eligible: 0,
      next_eligible_sell_date: "2025-01-01",
    });
  });

  it("falls back to null when no lot in the group has a usable acquired_date", () => {
    const undatedAccounts: Account[] = [
      {
        owner: "alice",
        account_type: "ISA",
        currency: "GBP",
        value_estimate_gbp: 100,
        holdings: [
          {
            ticker: "ZZZ",
            name: "Zeta",
            units: 1,
            cost_basis_gbp: 10,
            market_value_gbp: 12,
            gain_gbp: 2,
          },
        ],
      },
    ];

    const [row] = toRollupRows(toScopedHoldingRows(undatedAccounts));

    expect(row).toMatchObject({
      acquired_date: null,
      days_held: null,
      sell_eligible: null,
      days_until_eligible: null,
      next_eligible_sell_date: null,
    });
  });

  it("joins instrument fields by ticker and uses null for an unmatched row", () => {
    const instruments: InstrumentSummary[] = [
      {
        ticker: "AAA",
        name: "Alpha instrument",
        units: 3,
        market_value_gbp: 300,
        gain_gbp: 150,
        grouping: "Equity",
        exchange: "LSE",
        change_7d_pct: 2.5,
        change_30d_pct: null,
      },
    ];

    const [matched, unmatched] = toRollupRows(
      toScopedHoldingRows(accounts),
      instruments,
    );

    expect(matched).toMatchObject({
      grouping: "Equity",
      exchange: "LSE",
      change_7d_pct: 2.5,
      change_30d_pct: null,
    });
    expect(unmatched).toMatchObject({
      grouping: null,
      exchange: null,
      change_7d_pct: null,
      change_30d_pct: null,
    });
  });
});
