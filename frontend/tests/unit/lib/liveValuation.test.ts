import { describe, expect, it } from 'vitest';

import type { LiveQuote } from '@/api';
import { applyLiveQuotes } from '@/lib/liveValuation';
import type { Account, Holding } from '@/types';

const quote = (overrides: Partial<LiveQuote> = {}): LiveQuote => ({
  price: 12,
  price_gbp: 12,
  currency: 'GBP',
  previous_close: 11.5,
  change_pct: 4.347826086956522, // 12 vs 11.5
  timestamp: '2026-10-08T10:15:00Z',
  market_state: 'REGULAR',
  is_stale: false,
  ...overrides,
});

// 10 units at a stored £10: cost_for_gain £80 (gain £20 = 25%), invested £90
// (total return £30 incl. realised/income = 33.33%).
const holding = (overrides: Partial<Holding> = {}): Holding => ({
  ticker: 'VOD.L',
  name: 'Vodafone',
  units: 10,
  price: 10,
  current_price_gbp: 10,
  market_value_gbp: 100,
  gain_gbp: 20,
  gain_pct: 25,
  total_return_gbp: 30,
  total_return_pct: (30 / 90) * 100,
  day_change_gbp: 1,
  is_stale: true,
  instrument_type: 'Equity',
  ...overrides,
});

const account = (holdings: Holding[], value = 150): Account => ({
  account_type: 'ISA',
  currency: 'GBP',
  value_estimate_gbp: value,
  holdings,
});

describe('applyLiveQuotes', () => {
  it("revalues a holding with the backend's formulas", () => {
    const [acct] = applyLiveQuotes([account([holding()])], {
      'VOD.L': quote(),
    });
    const h = acct.holdings[0];

    expect(h.current_price_gbp).toBe(12);
    expect(h.price).toBe(12);
    expect(h.market_value_gbp).toBe(120);
    expect(h.gain_gbp).toBe(40);
    expect(h.gain_pct).toBeCloseTo(50); // 40 / 80
    expect(h.total_return_gbp).toBe(50);
    expect(h.total_return_pct).toBeCloseTo((50 / 90) * 100);
    expect(h.day_change_gbp).toBeCloseTo(5); // 10 x (12 - 11.5)
    expect(h.is_stale).toBe(false);
    expect(h.last_price_time).toBe('2026-10-08T10:15:00Z');
    // The account value moves by the market value delta (cash untouched).
    expect(acct.value_estimate_gbp).toBe(170);
  });

  it('matches tickers case-insensitively and leaves cash and unquoted holdings alone', () => {
    const cash = holding({
      ticker: 'CASH.GBP',
      instrument_type: 'Cash',
      market_value_gbp: 50,
    });
    const other = holding({ ticker: 'BP.L' });
    const [acct] = applyLiveQuotes(
      [account([holding({ ticker: 'vod.l' }), cash, other])],
      {
        'VOD.L': quote(),
        'CASH.GBP': quote({ price_gbp: 2 }),
      }
    );

    expect(acct.holdings[0].market_value_gbp).toBe(120);
    expect(acct.holdings[1]).toBe(cash);
    expect(acct.holdings[2]).toBe(other);
  });

  it('keeps unknown gains unknown and skips unpriced holdings', () => {
    const unknownCost = holding({
      gain_gbp: null,
      gain_pct: null,
      total_return_gbp: null,
      total_return_pct: null,
    });
    const unpriced = holding({ ticker: 'MISS.N', market_value_gbp: null });
    const [acct] = applyLiveQuotes([account([unknownCost, unpriced])], {
      'VOD.L': quote(),
      'MISS.N': quote(),
    });

    expect(acct.holdings[0].market_value_gbp).toBe(120);
    expect(acct.holdings[0].gain_gbp).toBeNull();
    expect(acct.holdings[0].total_return_pct).toBeNull();
    expect(acct.holdings[1]).toBe(unpriced);
  });

  it('keeps the stored day change when the quote has no previous close', () => {
    const [acct] = applyLiveQuotes([account([holding()])], {
      'VOD.L': quote({ change_pct: null }),
    });
    expect(acct.holdings[0].day_change_gbp).toBe(1);
  });

  it('returns the same array when no quote applies', () => {
    const accounts = [account([holding()])];
    expect(applyLiveQuotes(accounts, {})).toBe(accounts);
    expect(applyLiveQuotes(accounts, { 'BP.L': quote() })).toBe(accounts);
  });
});
