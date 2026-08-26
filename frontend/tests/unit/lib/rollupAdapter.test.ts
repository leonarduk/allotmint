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
        current_price_gbp: 60,
        current_price_currency: "GBP",
        currency: "GBP",
        instrument_type: "Equity",
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
        current_price_gbp: 60,
        current_price_currency: "GBP",
        currency: "GBP",
        instrument_type: "Equity",
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
      current_price_gbp: 60,
      current_price_currency: "GBP",
      currency: "GBP",
      instrument_type: "Equity",
    });
  });

  it("derives price/currency/instrument type from a representative lot when a ticker has multiple lots", () => {
    // AAA rolls up alice's and bob's lots. Both carry identical per-unit
    // price/currency/type, which is the expected shape (price is per-unit,
    // currency and instrument type are properties of the instrument, not the
    // position) -- the rollup should surface these rather than leaving them
    // blank, which was the bug: Px £/CCY/Type showed as "-"/blank/"Other" in
    // Rollup mode even though every lot carried real values.
    const [row] = toRollupRows(toScopedHoldingRows(accounts));

    expect(row).toMatchObject({
      ticker: "AAA",
      current_price_gbp: 60,
      current_price_currency: "GBP",
      currency: "GBP",
      instrument_type: "Equity",
    });
  });

  it("falls back to null when no lot in the group carries price/currency/type", () => {
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
      current_price_gbp: null,
      current_price_currency: null,
      currency: null,
      instrument_type: null,
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

  it("returns null days_held (not clamped to 0) when asOf predates the acquired_date", () => {
    // Regression: a historical `asOf` snapshot requested before the lot was
    // acquired must not be reported as "held for 0 days" — that reads as
    // "acquired today", which is misleading. It should surface as unavailable.
    const [row] = toRollupRows(
      toScopedHoldingRows(accounts),
      [],
      "2024-06-01", // before AAA's alice lot's acquired_date of 2025-01-01
    );

    expect(row).toMatchObject({
      ticker: "AAA",
      acquired_date: "2025-01-01",
      days_held: null,
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
