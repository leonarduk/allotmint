import type { Transaction, UnloggedChange } from '../types';
import { transactionUnits } from './transactionQuantity';

const QUALIFYING_TYPES = new Set(['BUY', 'SELL']);

/**
 * The facts of a just-saved trade worth prompting for, or ``null``.
 *
 * Mirrors the backend's ``decision_journal.capture.trade_change`` (#10481):
 * a dated BUY/SELL with an id, a ticker, a quantity and ``price_gbp``, worth
 * ``|units * price_gbp|`` (rounded to pence). Quantity uses
 * {@link transactionUnits}, so an imported Portfolio Performance row is
 * valued in real units.
 */
export function tradeChange(tx: Transaction): UnloggedChange | null {
  const type = String(tx.type ?? '').toUpperCase();
  const units = transactionUnits(tx);
  const price = tx.price_gbp;
  const date = String(tx.date ?? '').slice(0, 10);
  if (
    !QUALIFYING_TYPES.has(type) ||
    !tx.ticker ||
    !tx.id ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date)
  ) {
    return null;
  }
  if (units == null || price == null || !Number.isFinite(price)) return null;
  return {
    source_ref: tx.id,
    date,
    type: type as UnloggedChange['type'],
    ticker: tx.ticker.toUpperCase(),
    account: tx.account,
    amount_gbp: Math.round(Math.abs(units * price) * 100) / 100,
    price_gbp: price,
  };
}

/**
 * Trades just recorded or imported that reach the owner's journal threshold
 * (``settings.threshold_gbp`` from ``GET /decision-journal/{owner}``), in the
 * order given. Anything that is not a priced BUY/SELL never qualifies (#10488).
 */
export function qualifyingTrades(
  transactions: Transaction[],
  thresholdGbp: number
): UnloggedChange[] {
  return transactions
    .map(tradeChange)
    .filter(
      (change): change is UnloggedChange =>
        change !== null && change.amount_gbp >= thresholdGbp
    );
}
