import { describe, expect, it } from 'vitest';
import { qualifyingTrades, tradeChange } from '@/lib/decisionJournalPrompt';
import type { Transaction } from '@/types';

// Synthetic owner, tickers and amounts only.
const sell: Transaction = {
  id: 'alex:isa:3',
  owner: 'alex',
  account: 'isa',
  date: '2026-10-01',
  type: 'SELL',
  ticker: 'aaa.l',
  units: 40,
  price_gbp: 50.125,
};

describe('tradeChange', () => {
  it('values a priced SELL as |units x price_gbp| in pence', () => {
    expect(tradeChange(sell)).toEqual({
      source_ref: 'alex:isa:3',
      date: '2026-10-01',
      type: 'SELL',
      ticker: 'AAA.L',
      account: 'isa',
      amount_gbp: 2005,
      price_gbp: 50.125,
    });
  });

  it('scales Portfolio Performance shares to real units', () => {
    const row = { ...sell, units: null, shares: 4_000_000_000 };
    expect(tradeChange(row)?.amount_gbp).toBe(2005);
  });

  it.each([
    ['a dividend', { type: 'DIVIDEND' }],
    ['no id', { id: null }],
    ['no ticker', { ticker: null }],
    ['no price', { price_gbp: null }],
    ['no quantity', { units: null, shares: null }],
    ['no date', { date: null }],
  ])('ignores a transaction with %s', (_label, patch) => {
    expect(tradeChange({ ...sell, ...patch })).toBeNull();
  });
});

describe('qualifyingTrades', () => {
  const buy: Transaction = { ...sell, id: 'alex:isa:4', type: 'buy', units: 2 };

  it('keeps trades at or above the threshold, in the order given', () => {
    const atThreshold = { ...sell, id: 'alex:isa:5', units: 20, price_gbp: 50 };
    expect(
      qualifyingTrades([sell, buy, atThreshold], 1000).map((c) => c.source_ref)
    ).toEqual(['alex:isa:3', 'alex:isa:5']);
  });

  it('returns nothing when every trade is below the threshold', () => {
    expect(qualifyingTrades([sell, buy], 5000)).toEqual([]);
  });

  it('marks a BUY as BUY whatever its case', () => {
    expect(qualifyingTrades([buy], 0)[0].type).toBe('BUY');
  });
});
