import { describe, expect, it } from 'vitest';
import type { Alert, MoverRow, Transaction } from '@/types';
import {
  advanceVisitRecord,
  alertsSince,
  biggestMovers,
  buildSinceLastVisitDigest,
  dividendsSince,
  moversWindowDays,
  VISIT_SESSION_GAP_MS,
} from '@/lib/sinceLastVisit';

const DAY = 24 * 60 * 60 * 1000;
const NOW = Date.parse('2026-10-31T12:00:00Z');

const mover = (ticker: string, change_pct: number): MoverRow => ({
  ticker,
  name: ticker,
  change_pct,
});

const alert = (ticker: string, timestamp: string): Alert => ({
  ticker,
  change_pct: 5,
  message: `${ticker} moved`,
  timestamp,
});

const dividend = (overrides: Partial<Transaction>): Transaction => ({
  owner: 'alice',
  account: 'isa',
  type: 'DIVIDEND',
  date: '2026-10-30',
  amount_minor: 1234,
  currency: 'GBP',
  ...overrides,
});

describe('advanceVisitRecord', () => {
  it('treats a missing or malformed record as a first visit', () => {
    expect(advanceVisitRecord(null, NOW)).toEqual({ previous: null, current: NOW });
    expect(
      advanceVisitRecord({ current: 'x' as unknown as number }, NOW)
    ).toEqual({ previous: null, current: NOW });
  });

  it('rolls the current visit into previous after the session gap', () => {
    const current = NOW - VISIT_SESSION_GAP_MS - 1;
    expect(advanceVisitRecord({ previous: 1, current }, NOW)).toEqual({
      previous: current,
      current: NOW,
    });
  });

  it('keeps the previous visit on a reload within the session gap', () => {
    const previous = NOW - 7 * DAY;
    expect(advanceVisitRecord({ previous, current: NOW - 1000 }, NOW)).toEqual({
      previous,
      current: NOW,
    });
  });
});

describe('moversWindowDays', () => {
  it('picks the smallest supported window covering the gap', () => {
    expect(moversWindowDays(NOW - 2 * 60 * 60 * 1000, NOW)).toBe(1);
    expect(moversWindowDays(NOW - 3 * DAY, NOW)).toBe(7);
    expect(moversWindowDays(NOW - 8 * DAY, NOW)).toBe(30);
    expect(moversWindowDays(NOW - 1000 * DAY, NOW)).toBe(365);
  });
});

describe('biggestMovers', () => {
  it('ranks gainers and losers together by absolute move', () => {
    const rows = biggestMovers(
      {
        gainers: [mover('A', 2), mover('B', 6)],
        losers: [mover('C', -4), mover('D', -0.5), mover('E', Number.NaN)],
      },
      3
    );
    expect(rows.map((r) => r.ticker)).toEqual(['B', 'C', 'A']);
  });
});

describe('alertsSince', () => {
  const since = NOW - 2 * DAY;
  it('keeps alerts after the last visit for held tickers, newest first', () => {
    const result = alertsSince(
      [
        alert('VOD.L', '2026-10-30T09:00:00Z'),
        alert('HSBA', '2026-10-31T09:00:00Z'),
        alert('OLD', '2026-10-01T09:00:00Z'),
        alert('NOTHELD', '2026-10-31T10:00:00Z'),
        alert('BAD', 'not a date'),
      ],
      since,
      ['VOD.L', 'HSBA.L', 'OLD', 'BAD']
    );
    expect(result.map((a) => a.ticker)).toEqual(['HSBA', 'VOD.L']);
  });

  it('does not filter by ticker when holdings are unknown', () => {
    const result = alertsSince([alert('ANY', '2026-10-31T09:00:00Z')], since, []);
    expect(result).toHaveLength(1);
  });
});

describe('dividendsSince', () => {
  it('sums booked dividends per currency for owners in view since the visit day', () => {
    const since = Date.parse('2026-10-29T18:00:00Z');
    const delta = dividendsSince(
      [
        dividend({ date: '2026-10-29' }), // same day as the visit: included
        dividend({ date: '2026-10-30', amount_minor: 500, currency: 'USD' }),
        dividend({ date: '2026-10-28' }), // before the visit
        dividend({ owner: 'bob' }), // not in view
        dividend({ estimated: true }),
        dividend({ attribution_only: true }),
        dividend({ amount_minor: null }),
      ],
      since,
      ['Alice']
    );
    expect(delta).toEqual({ payments: 2, amounts: { GBP: 12.34, USD: 5 } });
  });
});

describe('buildSinceLastVisitDigest', () => {
  const base = {
    since: NOW - 3 * DAY,
    owners: ['alice'],
    heldTickers: ['VOD.L'],
  };

  it('composes each section and reports when something changed', () => {
    const digest = buildSinceLastVisitDigest({
      ...base,
      movers: { gainers: [mover('VOD.L', 3)], losers: [] },
      alerts: [alert('VOD.L', '2026-10-31T09:00:00Z')],
      dividends: [dividend({})],
    });
    expect(digest.movers?.map((m) => m.ticker)).toEqual(['VOD.L']);
    expect(digest.alerts).toHaveLength(1);
    expect(digest.dividends?.payments).toBe(1);
    expect(digest.nothingChanged).toBe(false);
  });

  it('keeps a failed source null and never calls that "nothing changed"', () => {
    const digest = buildSinceLastVisitDigest({
      ...base,
      movers: { gainers: [], losers: [] },
      alerts: null,
      dividends: [],
    });
    expect(digest.alerts).toBeNull();
    expect(digest.movers).toEqual([]);
    expect(digest.nothingChanged).toBe(false);
  });

  it('flags nothing changed when every source loaded empty', () => {
    const digest = buildSinceLastVisitDigest({
      ...base,
      movers: { gainers: [], losers: [] },
      alerts: [],
      dividends: [],
    });
    expect(digest.nothingChanged).toBe(true);
  });
});
