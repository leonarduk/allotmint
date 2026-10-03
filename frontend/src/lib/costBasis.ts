/**
 * cost_basis_source values whose cost (and therefore gain) must not be shown
 * or summed as fact. Keep in sync with COST_BASIS_UNRELIABLE_SOURCES in
 * backend/common/holding_utils.py; both sides pin the contents in a test
 * (frontend/tests/unit/lib/costBasis.test.ts and
 * tests/test_holding_utils_price_cost_basis.py).
 *
 * - "unknown": no booked cost and no acquisition date, so cost was set equal to
 *   market value as a last resort (#7220).
 * - "book_suspect": the booked cost implies a unit cost more than 20x away from
 *   the reference price (#8472).
 */
export const COST_BASIS_UNKNOWN = "unknown";
export const COST_BASIS_BOOK_SUSPECT = "book_suspect";

const UNRELIABLE_SOURCES: ReadonlySet<string> = new Set([
  COST_BASIS_UNKNOWN,
  COST_BASIS_BOOK_SUSPECT,
]);

export function isCostBasisUnreliable(source: string | null | undefined): boolean {
  return source != null && UNRELIABLE_SOURCES.has(source);
}
