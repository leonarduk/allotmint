import type { LiveQuote } from '../api';
import type { Account, Holding } from '../types';
import { isCashInstrument } from './instruments';

const round2 = (v: number) => Math.round(v * 100) / 100;
const isNum = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v);

/**
 * Revalue one holding at its live GBP price, mirroring the backend's formulas
 * (backend/common/holding_utils.py enrich_holding, position_returns.py):
 *
 * - market value = units x price; gain and total return move by the same
 *   delta, since cost and realised/income parts don't change intraday;
 * - gain_pct over cost_for_gain (= old market value - old gain);
 * - total_return_pct over the invested amount backed out of the old pair;
 * - day change = units x (price - previous close), the previous close taken
 *   in GBP at the live quote's own FX (price_gbp / (1 + change_pct)).
 *
 * Holdings with no stored market value (unpriced, e.g. a missing FX rate)
 * are left alone: their gain has no cost to move from.
 */
function revalue(
  h: Holding,
  quote: LiveQuote
): { holding: Holding; delta: number } | null {
  const units = h.units;
  const oldMarket = h.market_value_gbp;
  if (
    !isNum(units) ||
    units === 0 ||
    !isNum(oldMarket) ||
    !isNum(quote.price_gbp)
  )
    return null;

  const market = units * quote.price_gbp;
  const delta = market - oldMarket;
  const next: Holding = {
    ...h,
    price: quote.price_gbp,
    current_price_gbp: quote.price_gbp,
    market_value_gbp: round2(market),
    last_price_time: quote.timestamp,
    is_stale: quote.is_stale,
  };

  if (isNum(h.gain_gbp)) {
    const costForGain = oldMarket - h.gain_gbp;
    const gain = h.gain_gbp + delta;
    next.gain_gbp = round2(gain);
    if (isNum(h.gain_pct) && costForGain > 0)
      next.gain_pct = (gain / costForGain) * 100;
  }

  if (isNum(h.total_return_gbp)) {
    const total = h.total_return_gbp + delta;
    if (
      isNum(h.total_return_pct) &&
      h.total_return_gbp !== 0 &&
      h.total_return_pct !== 0
    ) {
      const invested = h.total_return_gbp / (h.total_return_pct / 100);
      next.total_return_pct = (total / invested) * 100;
    }
    next.total_return_gbp = round2(total);
  }

  if (isNum(quote.change_pct) && quote.change_pct > -100) {
    const previousGbp = quote.price_gbp / (1 + quote.change_pct / 100);
    next.day_change_gbp = round2(units * (quote.price_gbp - previousGbp));
  }

  return { holding: next, delta };
}

/**
 * Accounts with every non-cash holding that has a live quote revalued at it,
 * and each account's value estimate moved by the same amount. Everything the
 * dashboard derives from accounts (rows, rollups, totals, allocations) then
 * shows live figures. Returns the input untouched when no quote applies.
 */
export function applyLiveQuotes(
  accounts: Account[],
  quotes: Record<string, LiveQuote>
): Account[] {
  if (Object.keys(quotes).length === 0) return accounts;
  let changed = false;
  const result = accounts.map((account) => {
    let accountDelta = 0;
    let accountChanged = false;
    const holdings = (account.holdings ?? []).map((h) => {
      const quote = quotes[(h.ticker ?? '').toUpperCase()];
      if (
        !quote ||
        isCashInstrument({
          instrument_type: h.instrument_type,
          ticker: h.ticker,
        })
      ) {
        return h;
      }
      const revalued = revalue(h, quote);
      if (!revalued) return h;
      accountDelta += revalued.delta;
      accountChanged = true;
      return revalued.holding;
    });
    if (!accountChanged) return account;
    changed = true;
    return {
      ...account,
      holdings,
      value_estimate_gbp: round2(
        (account.value_estimate_gbp ?? 0) + accountDelta
      ),
    };
  });
  return changed ? result : accounts;
}
