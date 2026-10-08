import { describe, expect, it } from 'vitest';
import {
  DEFAULT_BENCHMARKS,
  addBenchmark,
  buildBenchmarkSeries,
  buildPortfolioSeries,
  normaliseTicker,
  parseStoredBenchmarks,
  plottable,
  removeBenchmark,
} from '@/lib/riskReturn';
import type { GroupRiskReturn } from '@/types';

const data: GroupRiskReturn = {
  group: 'all',
  days: 365,
  start: '2025-10-07',
  end: '2026-10-07',
  missing_members: [],
  points: [
    {
      kind: 'group',
      owner: null,
      account: null,
      period_return: 0.05,
      annualised_return: 0.049,
      volatility: 0.12,
    },
    {
      kind: 'owner',
      owner: 'steve',
      account: null,
      period_return: 0.1,
      annualised_return: 0.098,
      volatility: 0.2,
    },
    {
      kind: 'account',
      owner: 'steve',
      account: 'isa',
      period_return: -0.02,
      annualised_return: null,
      volatility: null,
    },
  ],
};

const options = {
  days: 365,
  ownerNames: new Map([['steve', 'Steve']]),
  groupLabel: 'Entire portfolio',
  ownerTotalLabel: (owner: string) => `${owner} (all accounts)`,
};

describe('riskReturn series', () => {
  it('labels and scales portfolio points to percent', () => {
    const series = buildPortfolioSeries(data, options);

    expect(series.map((s) => [s.id, s.label])).toEqual([
      ['group', 'Entire portfolio'],
      ['owner:steve', 'Steve (all accounts)'],
      ['account:steve:isa', 'Steve ISA'],
    ]);
    expect(series[1].returnPct).toBeCloseTo(10);
    expect(series[1].volatilityPct).toBeCloseTo(20);
    expect(plottable(series[2])).toBe(false);
  });

  it('uses the annualised return for windows longer than a year', () => {
    const series = buildPortfolioSeries(data, { ...options, days: 365 * 3 });

    expect(series[0].returnPct).toBeCloseTo(4.9);
    expect(series[2].returnPct).toBeNull();
  });

  it('builds benchmark series, null until a result arrives', () => {
    const series = buildBenchmarkSeries(
      DEFAULT_BENCHMARKS,
      {
        '^FTSE': {
          ticker: '^FTSE',
          days: 365,
          start: '',
          end: '',
          period_return: 0.08,
          annualised_return: null,
          volatility: 0.13,
        },
      },
      365,
      3
    );

    expect(series[0]).toMatchObject({
      id: 'benchmark:^FTSE',
      label: 'FTSE 100',
      kind: 'benchmark',
    });
    expect(series[0].returnPct).toBeCloseTo(8);
    expect(plottable(series[1])).toBe(false);
  });

  it('adds, dedupes and removes benchmarks', () => {
    const added = addBenchmark([], '^FTMC');
    expect(added).toEqual([{ ticker: '^FTMC', label: 'FTSE 250' }]);
    expect(addBenchmark(added, '^FTMC')).toBe(added);
    expect(addBenchmark(added, 'ABC.L')[1]).toEqual({
      ticker: 'ABC.L',
      label: 'ABC.L',
    });
    expect(removeBenchmark(added, '^FTMC')).toEqual([]);
  });

  it('normalises tickers', () => {
    expect(normaliseTicker(' ^ftse ')).toBe('^FTSE');
    expect(normaliseTicker('vwrl.l')).toBe('VWRL.L');
    expect(normaliseTicker('../etc')).toBeNull();
    expect(normaliseTicker('A..B')).toBeNull();
    expect(normaliseTicker('')).toBeNull();
  });

  it('falls back to the defaults for missing or corrupt storage', () => {
    expect(parseStoredBenchmarks(null)).toBe(DEFAULT_BENCHMARKS);
    expect(parseStoredBenchmarks('{oops')).toBe(DEFAULT_BENCHMARKS);
    expect(
      parseStoredBenchmarks(
        '[{"ticker":"^IXIC","label":"NASDAQ"},{"ticker":"bad ticker","label":"x"}]'
      )
    ).toEqual([{ ticker: '^IXIC', label: 'NASDAQ' }]);
    expect(parseStoredBenchmarks('[]')).toEqual([]);
  });
});
