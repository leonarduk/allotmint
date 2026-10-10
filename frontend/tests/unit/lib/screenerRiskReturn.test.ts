import { describe, expect, it } from 'vitest';
import {
  DEFAULT_RISK_FILTERS,
  hasRiskFilters,
  mergeRiskReturn,
  passesRiskFilters,
  riskColumnsFor,
  type ScreenerRow,
} from '@/lib/screenerRiskReturn';
import type { RiskReturnRow, ScreenerRiskReturn } from '@/types';

const stats = (sharpe: number, max_drawdown = -0.2) => ({
  return: 0.12,
  volatility: 0.16,
  sharpe,
  max_drawdown,
});

const row: RiskReturnRow = {
  ticker: 'VUSA.L',
  name: 'Vanguard S&P 500',
  currency: 'GBP',
  currency_source: 'metadata',
  return_basis: 'partial',
  first_date: '2013-05-22',
  last_date: '2026-10-08',
  windows: {
    '3': { gbp: stats(1.1), local: stats(1.0) },
    '5': { gbp: stats(0.9, -0.25), local: stats(0.8) },
    '10': { gbp: stats(0.85, -0.34), local: stats(0.7) },
  },
  notes: [],
};

describe('riskColumnsFor', () => {
  it("takes the lowest Sharpe and the selected period's figures", () => {
    const cols = riskColumnsFor(row, false, 'gbp', '5');
    expect(cols.min_sharpe).toBe(0.85);
    expect(cols.risk_max_drawdown).toBe(-0.25);
    expect(cols.risk_currency).toBe('GBP');
    expect(cols.risk_basis).toBe('partial');
    expect(cols.risk_status).toBe('ok');
  });

  it('leaves min Sharpe null when a period is missing', () => {
    const short = { ...row, windows: { ...row.windows, '10': null } };
    const cols = riskColumnsFor(short, false, 'gbp', '10');
    expect(cols.min_sharpe).toBeNull();
    expect(cols.sharpe_3y).toBe(1.1);
    expect(cols.risk_status).toBe('short');
  });

  it('reports why a ticker has no figures', () => {
    expect(riskColumnsFor(undefined, true, 'gbp', '10').risk_status).toBe(
      'missing'
    );
    expect(riskColumnsFor(undefined, false, 'gbp', '10').risk_status).toBe(
      'absent'
    );
  });
});

describe('mergeRiskReturn', () => {
  const data: ScreenerRiskReturn = {
    as_of: '2026-10-08',
    risk_free: { '3': 0.0449 },
    method: '',
    rows: [row],
    missing: [],
    fetched: [],
  };

  it('matches tickers case-insensitively', () => {
    const merged = mergeRiskReturn(
      [{ rank: 1, ticker: 'vusa.l' }],
      data,
      'local',
      '3'
    );
    expect(merged[0].sharpe_3y).toBe(1.0);
  });

  it('returns the rows untouched when there is no payload', () => {
    const rows = [{ rank: 1, ticker: 'VUSA.L' }];
    expect(mergeRiskReturn(rows, null, 'gbp', '10')).toBe(rows);
  });
});

describe('passesRiskFilters', () => {
  const merged: ScreenerRow = {
    rank: 1,
    ticker: 'VUSA.L',
    ...riskColumnsFor(row, false, 'gbp', '10'),
  };

  it('passes everything with no filters set', () => {
    expect(hasRiskFilters(DEFAULT_RISK_FILTERS)).toBe(false);
    expect(
      passesRiskFilters({ rank: 1, ticker: 'X' }, DEFAULT_RISK_FILTERS)
    ).toBe(true);
  });

  it('applies min Sharpe to all three or to one period', () => {
    const all = { ...DEFAULT_RISK_FILTERS, minSharpe: '0.9' };
    expect(passesRiskFilters(merged, all)).toBe(false);
    expect(passesRiskFilters(merged, { ...all, sharpeScope: '3' })).toBe(true);
  });

  it('treats the worst-fall limit as a size, whatever its sign', () => {
    const filters = { ...DEFAULT_RISK_FILTERS, maxDrawdown: '0.3' };
    expect(passesRiskFilters(merged, filters)).toBe(false);
    expect(passesRiskFilters(merged, { ...filters, maxDrawdown: '-0.4' })).toBe(
      true
    );
  });

  it('fails a row that lacks the figure a filter needs', () => {
    const filters = { ...DEFAULT_RISK_FILTERS, minSharpe: '0' };
    expect(passesRiskFilters({ rank: 1, ticker: 'X' }, filters)).toBe(false);
  });
});
