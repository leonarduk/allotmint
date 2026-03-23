import { describe, expect, it } from 'vitest';
import type { InstrumentGroupDefinition, InstrumentSummary } from '@/types';
import {
  buildCategoryLookup,
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

  it('deduplicates group options and parses ticker parts', () => {
    expect(mergeGroupOptions([' Income '], ['income', 'Growth', null])).toEqual([
      'Growth',
      'Income',
    ]);
    expect(splitTickerParts('VUSA')).toEqual({ ticker: 'VUSA', exchange: 'L' });
    expect(splitTickerParts('VUSA.N')).toEqual({ ticker: 'VUSA', exchange: 'N' });
  });
});
