import { describe, expect, it } from 'vitest';

import type { LiveQuote } from '@/api';
import i18n from '@/i18n';
import { closeAsOf, liveQuoteAsOf } from '@/lib/priceAsOf';

const t = i18n.t.bind(i18n);

const quote = (overrides: Partial<LiveQuote> = {}): LiveQuote => ({
  price: 1,
  price_gbp: 1,
  currency: 'GBP',
  previous_close: null,
  change_pct: null,
  timestamp: new Date().toISOString(),
  market_state: 'REGULAR',
  is_stale: false,
  ...overrides,
});

describe('liveQuoteAsOf', () => {
  it('labels a fresh in-session quote live with its time', () => {
    const asOf = liveQuoteAsOf(quote(), t);
    expect(asOf.kind).toBe('live');
    expect(asOf.label).toMatch(/^Live \d{2}:\d{2}( [AP]M)?$/);
  });

  it('labels an old in-session quote delayed', () => {
    expect(liveQuoteAsOf(quote({ is_stale: true }), t).kind).toBe('delayed');
  });

  it.each(['CLOSED', 'PRE', 'POST'])(
    'labels a %s-market quote as the close of its trading day',
    (market_state) => {
      const asOf = liveQuoteAsOf(
        quote({
          market_state,
          timestamp: '2026-10-07T15:30:00Z',
          is_stale: true,
        }),
        t
      );
      expect(asOf.kind).toBe('close');
      expect(asOf.label).toBe('Close 2026-10-07');
    }
  );

  it('treats an unknown market state by freshness alone', () => {
    expect(liveQuoteAsOf(quote({ market_state: null }), t).kind).toBe('live');
    expect(
      liveQuoteAsOf(quote({ market_state: null, is_stale: true }), t).kind
    ).toBe('delayed');
  });

  it('shows the date for an in-session quote from another day', () => {
    const asOf = liveQuoteAsOf(
      quote({ timestamp: '2026-10-07T10:15:00Z', is_stale: true }),
      t
    );
    expect(asOf.label).toMatch(/^Delayed 2026-10-07 \d{2}:\d{2}( [AP]M)?$/);
  });
});

describe('closeAsOf', () => {
  it('labels a stored price as the close of its date', () => {
    expect(closeAsOf('2026-10-06', t)).toEqual({
      kind: 'close',
      label: 'Close 2026-10-06',
      title: '2026-10-06',
    });
  });

  it('returns null without a date', () => {
    expect(closeAsOf(null, t)).toBeNull();
    expect(closeAsOf(undefined, t)).toBeNull();
  });
});
