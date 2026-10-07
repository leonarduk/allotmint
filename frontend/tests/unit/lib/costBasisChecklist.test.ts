import { describe, expect, it } from 'vitest';
import {
  buildCostBasisChecklist,
  costBasisFillHref,
  topValueShare,
} from '@/lib/costBasisChecklist';
import type { Account, Holding } from '@/types';

function holding(overrides: Partial<Holding>): Holding {
  return {
    ticker: 'ABC.L',
    name: 'Test Holding',
    units: 10,
    market_value_gbp: 100,
    cost_basis_source: 'unknown',
    ...overrides,
  };
}

function account(
  owner: string,
  account_type: string,
  holdings: Holding[]
): Account {
  return {
    owner,
    account_type,
    currency: 'GBP',
    value_estimate_gbp: 0,
    holdings,
  };
}

describe('buildCostBasisChecklist', () => {
  it('lists only unreliable cost bases, largest market value first, unpriced last', () => {
    const gaps = buildCostBasisChecklist([
      account('alex', 'isa', [
        holding({ ticker: 'SMALL.L', market_value_gbp: 50 }),
        holding({
          ticker: 'BOOKED.L',
          market_value_gbp: 9999,
          cost_basis_source: 'book',
        }),
        holding({ ticker: 'NOPRICE.L', market_value_gbp: null }),
      ]),
      account('sam', 'sipp', [
        holding({
          ticker: 'BIG.L',
          market_value_gbp: 5000,
          cost_basis_source: 'book_suspect',
        }),
        holding({
          ticker: 'CASH.GBP',
          market_value_gbp: 700,
          cost_basis_source: 'cash',
        }),
      ]),
    ]);

    expect(gaps.map((g) => g.ticker)).toEqual([
      'BIG.L',
      'SMALL.L',
      'NOPRICE.L',
    ]);
    expect(gaps[0]).toMatchObject({
      owner: 'sam',
      account: 'sipp',
      marketValue: 5000,
      source: 'book_suspect',
    });
    expect(gaps[2].marketValue).toBeNull();
  });

  it('keeps several unpriced gaps after every priced one, in input order', () => {
    const gaps = buildCostBasisChecklist([
      account('alex', 'isa', [
        holding({ ticker: 'NONE1.L', market_value_gbp: null }),
        holding({ ticker: 'NONE2.L', market_value_gbp: null }),
        holding({ ticker: 'PRICED.L', market_value_gbp: 1 }),
        holding({ ticker: 'NONE3.L', market_value_gbp: null }),
      ]),
    ]);

    expect(gaps.map((g) => g.ticker)).toEqual([
      'PRICED.L',
      'NONE1.L',
      'NONE2.L',
      'NONE3.L',
    ]);
  });

  it('returns an empty list when every cost basis is reliable', () => {
    expect(
      buildCostBasisChecklist([
        account('alex', 'isa', [holding({ cost_basis_source: 'book' })]),
      ])
    ).toEqual([]);
  });
});

describe('topValueShare', () => {
  it('is the fraction of gap value held by the first N gaps', () => {
    const gaps = buildCostBasisChecklist([
      account('alex', 'isa', [
        holding({ ticker: 'A', market_value_gbp: 600 }),
        holding({ ticker: 'B', market_value_gbp: 300 }),
        holding({ ticker: 'C', market_value_gbp: 100 }),
      ]),
    ]);
    expect(topValueShare(gaps, 1)).toBeCloseTo(0.6);
    expect(topValueShare(gaps, 10)).toBe(1);
  });

  it('is zero when no gap has a value', () => {
    expect(topValueShare([], 10)).toBe(0);
  });
});

describe('costBasisFillHref', () => {
  it('links to the set-holding form prefilled with the holding', () => {
    const [gap] = buildCostBasisChecklist([
      account('alex', 'isa', [holding({ ticker: 'VUSA.L', units: 12.5 })]),
    ]);
    const url = new URL(costBasisFillHref(gap), 'http://x');
    expect(url.pathname).toBe('/input');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      owner: 'alex',
      account: 'isa',
      ticker: 'VUSA.L',
      units: '12.5',
    });
  });
});
