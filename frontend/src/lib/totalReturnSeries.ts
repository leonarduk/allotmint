import type { PerformancePoint } from '../types';

/** `cumulative_return_basis` values from /performance/{owner} and /performance-group/{slug} (#10128). */
export const CUMULATIVE_RETURN_BASIS_LEDGER = 'ledger_total_return';
export const CUMULATIVE_RETURN_BASIS_UNAVAILABLE = 'unavailable';

/**
 * Adds `total_return` to each benchmark-comparison point (#10128): the
 * ledger total return from the history (price moves plus dividends and
 * interest, net of deposits and withdrawals), rebased to the first
 * comparison date that has one, so all three lines start at 0 together.
 * Dates the history does not cover get `null`, never a made-up 0.
 */
export function withTotalReturn<T extends { date: string }>(
  points: T[],
  history: PerformancePoint[]
): (T & { total_return: number | null })[] {
  const byDate = new Map<string, number>();
  for (const row of history) {
    if (
      typeof row.cumulative_return === 'number' &&
      Number.isFinite(row.cumulative_return)
    ) {
      byDate.set(row.date, row.cumulative_return);
    }
  }
  const base = points
    .map((p) => byDate.get(p.date))
    .find((v) => v !== undefined);
  return points.map((p) => {
    const value = byDate.get(p.date);
    return {
      ...p,
      total_return:
        value === undefined || base === undefined
          ? null
          : (1 + value) / (1 + base) - 1,
    };
  });
}
