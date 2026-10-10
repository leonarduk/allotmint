import { describe, expect, it } from 'vitest';
import {
  DEFAULT_BENCHMARKS,
  addBenchmark,
  averageLine,
  buildBenchmarkSeries,
  buildPortfolioSeries,
  isIndexSeries,
  normaliseTicker,
  parseRiskFreePct,
  parseStoredBenchmarks,
  plottable,
  removeBenchmark,
  seriesDetails,
  sharpeRatio,
  sideOfAverage,
  type ChartSeries,
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
    expect(series[1].sharpeReturnPct).toBeNull();
    expect(
      buildPortfolioSeries(
        {
          ...data,
          points: [{ ...data.points[1], sharpe_annual_return: 0.101 }],
        },
        options
      )[0].sharpeReturnPct
    ).toBeCloseTo(10.1);
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

describe('average line', () => {
  const point = (
    id: string,
    volatilityPct: number | null,
    returnPct: number | null
  ): ChartSeries => ({
    id,
    label: id,
    kind: 'account',
    color: '#000',
    volatilityPct,
    returnPct,
  });

  it('runs from the origin through the mean of the plottable points', () => {
    const line = averageLine([
      point('a', 10, 5),
      point('b', 20, 15),
      point('c', null, 99),
    ]);

    expect(line).not.toBeNull();
    expect(line!.volatilityPct).toBeCloseTo(15);
    expect(line!.returnPct).toBeCloseTo(10);
    expect(line!.slope).toBeCloseTo(10 / 15);
    expect(line!.interceptPct).toBe(0);
  });

  it('starts from the risk-free rate, so its slope is the average Sharpe ratio', () => {
    const line = averageLine([point('a', 10, 5), point('b', 20, 15)], 4)!;

    expect(line.interceptPct).toBe(4);
    expect(line.slope).toBeCloseTo((10 - 4) / 15);
    expect(line.slope).toBeCloseTo(sharpeRatio(15, 10, 4)!);
    // On the line at 10% volatility the return is 4 + 0.4 * 10 = 8%.
    expect(sideOfAverage(line, 10, 8)).toBe('on');
    expect(sideOfAverage(line, 10, 8.5)).toBe('above');
    expect(sideOfAverage(line, 10, 7)).toBe('below');
    // A low-volatility point that beats the 0% line can fall below this one.
    const fromOrigin = averageLine([point('a', 10, 5), point('b', 20, 15)])!;
    expect(sideOfAverage(fromOrigin, 5, 4)).toBe('above');
    expect(sideOfAverage(line, 5, 4)).toBe('below');
  });

  it('needs two points and a positive mean volatility', () => {
    expect(averageLine([point('a', 10, 5)])).toBeNull();
    expect(averageLine([point('a', 0, 5), point('b', 0, 1)])).toBeNull();
  });

  it('classifies points above and below the line', () => {
    const line = averageLine([point('a', 10, 5), point('b', 20, 15)])!;

    expect(sideOfAverage(line, 10, 8)).toBe('above');
    expect(sideOfAverage(line, 20, 5)).toBe('below');
    expect(sideOfAverage(line, 15, 10)).toBe('on');
  });
});

describe('series details', () => {
  const benchmark = (ticker: string, extra: Partial<ChartSeries> = {}) =>
    ({
      id: `benchmark:${ticker}`,
      label: ticker,
      kind: 'benchmark',
      color: '#000',
      returnPct: 5,
      volatilityPct: 10,
      ...extra,
    }) as ChartSeries;

  it('carries the instrument name and sector of a listed ticker', () => {
    const [series] = buildBenchmarkSeries(
      [{ ticker: 'FCIT.L', label: 'FCIT.L' }],
      {
        'FCIT.L': {
          ticker: 'FCIT.L',
          days: 365,
          start: '',
          end: '',
          name: 'F&C Investment Trust',
          sector: 'Global',
          period_return: 0.1,
          annualised_return: null,
          volatility: 0.15,
        },
      },
      365,
      0
    );

    expect(seriesDetails(series, 'Market index')).toEqual({
      name: 'F&C Investment Trust',
      sector: 'Global',
    });
  });

  it('describes an index symbol as a market index', () => {
    expect(seriesDetails(benchmark('^FTSE'), 'Market index')).toEqual({
      name: null,
      sector: 'Market index',
    });
  });

  it('omits a name that repeats the label and has no sector for accounts', () => {
    expect(
      seriesDetails(benchmark('VWRL.L', { name: 'VWRL.L' }), 'Market index')
    ).toEqual({ name: null, sector: null });
    expect(
      seriesDetails(
        { ...benchmark('x'), id: 'group', kind: 'group' },
        'Market index'
      )
    ).toEqual({ name: null, sector: null });
  });
});

describe('sharpe ratio and risk-free rate', () => {
  it('is excess return per unit of volatility', () => {
    expect(sharpeRatio(10, 8, 4)).toBeCloseTo(0.4);
    expect(sharpeRatio(10, 2, 4)).toBeCloseTo(-0.2);
    expect(sharpeRatio(0, 8, 4)).toBeNull();
    expect(sharpeRatio(10, null, 4)).toBeNull();
    expect(sharpeRatio(10, undefined, 4)).toBeNull();
  });

  it('parses a typed risk-free rate within bounds', () => {
    expect(parseRiskFreePct(' 4.25 ')).toBe(4.25);
    expect(parseRiskFreePct('0')).toBe(0);
    expect(parseRiskFreePct('')).toBeNull();
    expect(parseRiskFreePct(null)).toBeNull();
    expect(parseRiskFreePct('abc')).toBeNull();
    expect(parseRiskFreePct('30')).toBeNull();
  });

  it('tells index symbols from listed tickers and portfolio points', () => {
    const series = (id: string, kind: ChartSeries['kind']): ChartSeries => ({
      id,
      label: id,
      kind,
      color: '#000',
      returnPct: 1,
      volatilityPct: 1,
    });
    expect(isIndexSeries(series('benchmark:^FTSE', 'benchmark'))).toBe(true);
    expect(isIndexSeries(series('benchmark:VWRL.L', 'benchmark'))).toBe(false);
    expect(isIndexSeries(series('group', 'group'))).toBe(false);
  });
});
