import { describe, expect, it } from 'vitest';
import {
  holdingsFromAccounts,
  periodLabel,
  summariseDividends,
} from '@/lib/dividends';
import type { Account, Transaction } from '@/types';

const div = (overrides: Partial<Transaction>): Transaction => ({
  owner: 'alex',
  account: 'isa',
  type: 'DIVIDEND',
  currency: 'GBP',
  ...overrides,
});

const NOW = new Date('2026-10-07T12:00:00Z');

describe('periodLabel', () => {
  it('splits UK tax years on 6 April', () => {
    expect(periodLabel(new Date('2026-04-05T00:00:00Z'), 'taxYear')).toBe(
      '2025/26'
    );
    expect(periodLabel(new Date('2026-04-06T00:00:00Z'), 'taxYear')).toBe(
      '2026/27'
    );
    expect(periodLabel(new Date('1999-12-01T00:00:00Z'), 'taxYear')).toBe(
      '1999/00'
    );
  });

  it('labels calendar years and months', () => {
    expect(periodLabel(new Date('2026-03-09T00:00:00Z'), 'year')).toBe('2026');
    expect(periodLabel(new Date('2026-03-09T00:00:00Z'), 'month')).toBe(
      '2026-03'
    );
  });
});

describe('summariseDividends', () => {
  it('totals by period newest first, with a trailing-12-month figure', () => {
    const summary = summariseDividends(
      [
        div({ date: '2026-09-01', amount_minor: 1000, ticker: 'vwrl.l' }),
        div({ date: '2025-11-01', amount_minor: 500, ticker: 'VWRL.L' }),
        div({ date: '2024-05-01', amount_minor: 250 }),
      ],
      { period: 'year', now: NOW }
    );

    expect(summary.total).toEqual({ GBP: 17.5 });
    expect(summary.trailing12m).toEqual({ GBP: 15 });
    expect(
      summary.periods.map((p) => [p.period, p.amounts.GBP, p.payments])
    ).toEqual([
      ['2026', 10, 1],
      ['2025', 5, 1],
      ['2024', 2.5, 1],
    ]);
  });

  it('excludes payments exactly one year old from the trailing figure', () => {
    const summary = summariseDividends(
      [
        div({ date: '2025-10-07', amount_minor: 100 }),
        div({ date: '2025-10-08', amount_minor: 200 }),
      ],
      { period: 'year', now: NOW }
    );
    expect(summary.trailing12m).toEqual({ GBP: 2 });
  });

  it('never adds amounts in different currencies together', () => {
    const summary = summariseDividends(
      [
        div({ date: '2026-01-01', amount_minor: 1000, currency: 'GBP' }),
        div({ date: '2026-01-02', amount_minor: 300, currency: 'USD' }),
      ],
      { period: 'month', now: NOW }
    );
    expect(summary.total).toEqual({ GBP: 10, USD: 3 });
    expect(summary.periods[0].amounts).toEqual({ GBP: 10, USD: 3 });
  });

  it('keeps ticker-less payments in an unattributed row rather than dropping them', () => {
    const summary = summariseDividends(
      [
        div({ date: '2026-02-01', amount_minor: 400 }),
        div({ date: '2026-03-01', amount_minor: 600, ticker: 'ABC' }),
      ],
      { period: 'year', now: NOW }
    );
    expect(
      summary.holdings.map((h) => [h.ticker, h.total.GBP, h.lastPaid])
    ).toEqual([
      ['ABC', 6, '2026-03-01'],
      [null, 4, '2026-02-01'],
    ]);
  });

  it('lists held tickers with no dividend rows as having no history, not a zero amount', () => {
    const summary = summariseDividends(
      [div({ date: '2026-03-01', amount_minor: 600, ticker: 'ABC' })],
      {
        period: 'year',
        now: NOW,
        holdings: new Map([
          ['ABC', 'Abc plc'],
          ['XYZ', 'Xyz Growth'],
        ]),
      }
    );
    const xyz = summary.holdings.find((h) => h.ticker === 'XYZ');
    expect(xyz).toMatchObject({
      payments: 0,
      total: {},
      trailing12m: {},
      lastPaid: null,
    });
    expect(summary.holdings.find((h) => h.ticker === 'ABC')?.name).toBe(
      'Abc plc'
    );
    // Paying holdings sort ahead of those with no history.
    expect(summary.holdings.map((h) => h.ticker)).toEqual(['ABC', 'XYZ']);
  });

  it('skips rows with no amount and puts undated rows in a trailing bucket', () => {
    const summary = summariseDividends(
      [
        div({ date: null, amount_minor: 100 }),
        div({ date: '2026-01-01', amount_minor: null }),
      ],
      { period: 'year', now: NOW }
    );
    expect(summary.payments).toBe(1);
    expect(summary.trailing12m).toEqual({});
    expect(summary.periods).toEqual([
      { period: '', amounts: { GBP: 1 }, payments: 1 },
    ]);
  });
});

describe('holdingsFromAccounts', () => {
  it('collects distinct upper-cased tickers across accounts, skipping cash', () => {
    const accounts = [
      { holdings: [{ ticker: 'abc', name: 'Abc plc' }] },
      {
        holdings: [
          { ticker: 'ABC', name: 'Other' },
          { ticker: 'XYZ', name: '' },
          { ticker: 'CASH.GBP', name: 'Cash (GBP)' },
          { ticker: 'MMF', name: 'Money fund', instrument_type: 'cash' },
        ],
      },
    ] as unknown as Account[];
    expect([...holdingsFromAccounts(accounts)]).toEqual([
      ['ABC', 'Abc plc'],
      ['XYZ', null],
    ]);
  });
});
