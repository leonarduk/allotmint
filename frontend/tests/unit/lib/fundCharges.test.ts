import { describe, expect, it } from 'vitest';
import { computeFundCharges } from '@/lib/fundCharges';
import type { Account, Holding } from '@/types';

function holding(overrides: Partial<Holding>): Holding {
  return {
    ticker: 'ABC.L',
    name: 'Fund',
    units: 1,
    market_value_gbp: 1000,
    ...overrides,
  };
}

function account(holdings: Holding[]): Account {
  return {
    account_type: 'ISA',
    currency: 'GBP',
    value_estimate_gbp: 0,
    holdings,
  };
}

describe('computeFundCharges (#7834)', () => {
  it('value-weights known charges and estimates the annual cost', () => {
    const charges = computeFundCharges([
      account([
        holding({
          ticker: 'A.L',
          market_value_gbp: 3000,
          ongoing_charge_pct: 0.2,
        }),
        holding({
          ticker: 'B.L',
          market_value_gbp: 1000,
          ongoing_charge_pct: 1.0,
        }),
      ]),
    ]);
    expect(charges.annualCostGbp).toBeCloseTo(16);
    expect(charges.weightedChargePct).toBeCloseTo(0.4);
    expect(charges.holdingCount).toBe(2);
    expect(charges.unknownCount).toBe(0);
  });

  it('excludes holdings with no fee data rather than counting them as 0%', () => {
    const charges = computeFundCharges([
      account([
        holding({
          ticker: 'A.L',
          market_value_gbp: 1000,
          ongoing_charge_pct: 0.5,
        }),
        holding({
          ticker: 'B.L',
          market_value_gbp: 9000,
          ongoing_charge_pct: null,
        }),
        holding({ ticker: 'C.L', market_value_gbp: 500 }),
      ]),
    ]);
    expect(charges.weightedChargePct).toBeCloseTo(0.5);
    expect(charges.annualCostGbp).toBeCloseTo(5);
    expect(charges.unknownCount).toBe(2);
    expect(charges.holdingCount).toBe(3);
  });

  it('reports unknown (null) when no holding has fee data', () => {
    const charges = computeFundCharges([
      account([holding({ ongoing_charge_pct: undefined })]),
    ]);
    expect(charges.weightedChargePct).toBeNull();
    expect(charges.annualCostGbp).toBeNull();
  });

  it('keeps a genuine 0% charge distinct from unknown', () => {
    const charges = computeFundCharges([
      account([holding({ ongoing_charge_pct: 0 })]),
    ]);
    expect(charges.weightedChargePct).toBe(0);
    expect(charges.annualCostGbp).toBe(0);
    expect(charges.unknownCount).toBe(0);
  });

  it('treats negative or implausible charges as unknown, matching the backend', () => {
    const charges = computeFundCharges([
      account([
        holding({
          ticker: 'A.L',
          market_value_gbp: 1000,
          ongoing_charge_pct: 0.5,
        }),
        holding({
          ticker: 'B.L',
          market_value_gbp: 1000,
          ongoing_charge_pct: -0.3,
        }),
        holding({
          ticker: 'C.L',
          market_value_gbp: 1000,
          ongoing_charge_pct: 22,
        }),
      ]),
    ]);
    expect(charges.weightedChargePct).toBeCloseTo(0.5);
    expect(charges.annualCostGbp).toBeCloseTo(5);
    expect(charges.unknownCount).toBe(2);
    expect(charges.holdingCount).toBe(3);
  });

  it('ignores cash and unpriced holdings', () => {
    const charges = computeFundCharges([
      account([
        holding({
          ticker: 'CASH.GBP',
          instrument_type: 'cash',
          market_value_gbp: 5000,
        }),
        holding({
          ticker: 'X.L',
          market_value_gbp: null,
          ongoing_charge_pct: 0.3,
        }),
      ]),
    ]);
    expect(charges.holdingCount).toBe(0);
    expect(charges.weightedChargePct).toBeNull();
  });
});
