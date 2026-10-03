import { describe, expect, it } from 'vitest';
import type { InstrumentGroupDefinition, InstrumentSummary } from '@/types';
import {
  buildCategoryLookup,
  calculateGroupTotals,
  createGroups,
  createRowsWithCost,
  filterRowsByExchange,
  mergeGroupOptions,
  splitTickerParts,
} from '@/components/instrumentTable/utils';

const rows: InstrumentSummary[] = [
  {
    ticker: 'AAA',
    name: 'Alpha',
    grouping: 'Dividend Growth',
    exchange: 'L',
    currency: 'GBP',
    units: 10,
    market_value_gbp: 1000,
    gain_gbp: 100,
    change_7d_pct: 1,
  },
  {
    ticker: 'BBB',
    name: 'Beta',
    grouping: 'Global Tech',
    exchange: 'N',
    currency: 'USD',
    units: 5,
    market_value_gbp: 500,
    gain_gbp: -50,
    change_7d_pct: -2,
  },
];

describe('instrumentTable utils', () => {
  it('filters exchanges and preserves exchange-less rows', () => {
    const result = filterRowsByExchange(
      [...rows, { ...rows[0], ticker: 'CASH', exchange: null }],
      ['L', 'N'],
      ['N'],
    );

    expect(result.map((row) => row.ticker)).toEqual(['BBB', 'CASH']);
  });

  it('groups rows by category aliases and calculates totals', () => {
    const definitions: InstrumentGroupDefinition[] = [
      {
        id: 'dividend-growth',
        name: 'Dividend Growth',
        aliases: ['Dividend Growth'],
        category: 'income-strategies',
        category_name: 'Income Strategies',
      },
    ];

    const lookup = buildCategoryLookup(definitions);
    const grouped = createGroups(createRowsWithCost(rows), 'ticker', true, 'category', {
      ungroupedLabel: 'Ungrouped',
      uncategorisedLabel: 'Uncategorised',
    }, lookup);

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ label: 'Income Strategies' });
    expect(grouped[0]?.totals.marketValue).toBe(1000);
    expect(grouped[1]).toMatchObject({ label: 'Uncategorised' });
  });

  it('groups rows by sector case-insensitively with an unknown-sector bucket (#8486)', () => {
    const sectorRows: InstrumentSummary[] = [
      { ...rows[0], ticker: 'AV.L', sector: 'Financials' },
      { ...rows[1], ticker: 'BAC', sector: 'financials' },
      { ...rows[0], ticker: 'ZZZ', sector: null, market_value_gbp: 10, gain_gbp: 0 },
    ];

    const grouped = createGroups(createRowsWithCost(sectorRows), 'market_value_gbp', false, 'sector', {
      ungroupedLabel: 'Ungrouped',
      uncategorisedLabel: 'Uncategorised',
      unknownSectorLabel: 'Unknown sector',
    }, buildCategoryLookup([]));

    expect(grouped.map((group) => group.label)).toEqual(['Financials', 'Unknown sector']);
    expect(grouped[0]?.rows.map((row) => row.ticker)).toEqual(['AV.L', 'BAC']);
    expect(grouped[0]?.totals.marketValue).toBe(1500);
  });

  it('deduplicates group options and parses ticker parts', () => {
    expect(mergeGroupOptions([' Income '], ['income', 'Growth', null])).toEqual([
      'Growth',
      'Income',
    ]);
    expect(splitTickerParts('VUSA')).toEqual({ ticker: 'VUSA', exchange: 'L' });
    expect(splitTickerParts('VUSA.N')).toEqual({ ticker: 'VUSA', exchange: 'N' });
  });
});

describe('calculateGroupTotals with unknown cost basis (#7785)', () => {
  const base: InstrumentSummary = {
    ticker: 'A',
    name: 'A',
    units: 1,
    market_value_gbp: 1000,
    gain_gbp: 100,
  };

  it('leaves unknown-cost rows out of cost, gain and gain %', () => {
    const rows = createRowsWithCost([
      base,
      { ...base, ticker: 'B', market_value_gbp: 5000, gain_gbp: 0, cost_basis_source: 'unknown' },
    ]);
    const totals = calculateGroupTotals(rows, 'All');
    expect(totals.marketValue).toBe(6000);
    expect(totals.cost).toBe(900);
    expect(totals.gain).toBe(100);
    expect(totals.gainPct).toBeCloseTo((100 / 900) * 100);
  });

  it('leaves book_suspect rows out of cost, gain and gain % (#8472)', () => {
    const rows = createRowsWithCost([
      base,
      // Backend rollup row for AV.: cost/gain exclude the suspect holding.
      { ...base, ticker: 'AV', market_value_gbp: 33620, gain_gbp: 0, cost_basis_source: 'book_suspect' },
    ]);
    const totals = calculateGroupTotals(rows, 'All');
    expect(totals.marketValue).toBe(34620);
    expect(totals.cost).toBe(900);
    expect(totals.gain).toBe(100);
    expect(totals.gainPct).toBeCloseTo((100 / 900) * 100);
  });

  it('returns null gain and cost when no row has a reliable cost basis (#8531)', () => {
    const rows = createRowsWithCost([
      { ...base, ticker: 'AV', market_value_gbp: 33920, gain_gbp: 0, cost_basis_source: 'book_suspect' },
      { ...base, ticker: 'B', market_value_gbp: 500, gain_gbp: 0, cost_basis_source: 'unknown' },
    ]);
    const totals = calculateGroupTotals(rows, 'Financial Services');
    expect(totals.marketValue).toBe(34420);
    expect(totals.gain).toBeNull();
    expect(totals.cost).toBeNull();
    expect(totals.gainPct).toBeNull();
  });

  it('counts distinct tickers so callers can suppress cross-instrument unit sums (#8531)', () => {
    const rows = createRowsWithCost([base, { ...base, units: 4 }, { ...base, ticker: 'B', units: 2 }]);
    expect(calculateGroupTotals(rows, 'All').instrumentCount).toBe(2);
    expect(calculateGroupTotals(rows.slice(0, 2), 'A').instrumentCount).toBe(1);
  });

  it('sorts groups with null gain last in both directions (#8531)', () => {
    const groupRows = createRowsWithCost([
      { ...base, ticker: 'U', grouping: 'Unreliable', gain_gbp: 0, cost_basis_source: 'unknown' },
      { ...base, ticker: 'L', grouping: 'Loss', gain_gbp: -50 },
      { ...base, ticker: 'G', grouping: 'Gain', gain_gbp: 200 },
    ]);
    const labels = { ungroupedLabel: 'Ungrouped', uncategorisedLabel: 'Uncategorised' };
    const lookup = buildCategoryLookup([]);
    const descending = createGroups(groupRows, 'gain_gbp', false, 'group', labels, lookup);
    expect(descending.map((group) => group.label)).toEqual(['Gain', 'Loss', 'Unreliable']);
    const ascending = createGroups(groupRows, 'gain_gbp', true, 'group', labels, lookup);
    expect(ascending.map((group) => group.label)).toEqual(['Loss', 'Gain', 'Unreliable']);
  });

  it('sorts groups with NaN or missing totals last in both directions (#8531)', () => {
    const labels = { ungroupedLabel: 'Ungrouped', uncategorisedLabel: 'Uncategorised' };
    const lookup = buildCategoryLookup([]);

    // NaN market value propagates into the group's marketValue total.
    const marketRows = createRowsWithCost([
      { ...base, ticker: 'N', grouping: 'NaN', market_value_gbp: Number.NaN },
      { ...base, ticker: 'S', grouping: 'Small', market_value_gbp: 100 },
      { ...base, ticker: 'B', grouping: 'Big', market_value_gbp: 5000 },
    ]);
    for (const asc of [true, false]) {
      const sorted = createGroups(marketRows, 'market_value_gbp', asc, 'group', labels, lookup);
      expect(sorted.at(-1)?.label).toBe('NaN');
    }

    // No 7d change on any row leaves the group's change7dPct missing.
    const changeRows = createRowsWithCost([
      { ...base, ticker: 'M', grouping: 'Missing', change_7d_pct: undefined },
      { ...base, ticker: 'D', grouping: 'Down', change_7d_pct: -3 },
      { ...base, ticker: 'U', grouping: 'Up', change_7d_pct: 4 },
    ]);
    const ascending = createGroups(changeRows, 'change_7d_pct', true, 'group', labels, lookup);
    expect(ascending.map((group) => group.label)).toEqual(['Down', 'Up', 'Missing']);
    const descending = createGroups(changeRows, 'change_7d_pct', false, 'group', labels, lookup);
    expect(descending.map((group) => group.label)).toEqual(['Up', 'Down', 'Missing']);
  });
});
