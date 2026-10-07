import type { Transaction } from "../types";

/**
 * Portfolio Performance stores share counts as fixed-point integers
 * (real units × 10^8); imported rows keep that value in ``shares``.
 */
export const PP_SHARE_SCALE = 1e8;

const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

/**
 * Real-unit quantity a transaction records, or ``null`` if unknown.
 *
 * Mirrors the backend's ``holdings_rebuild.transaction_quantity`` (#7920):
 * scale is decided by field, never by magnitude.  ``units`` holds real units
 * and wins (an app edit sets it on a PP row); ``shares`` is always PP's
 * fixed-point count and is divided by 10^8.
 */
export function transactionUnits(
  tx: Pick<Transaction, "units" | "shares">,
): number | null {
  if (tx.units != null) return finite(tx.units);
  const shares = finite(tx.shares);
  return shares == null ? null : shares / PP_SHARE_SCALE;
}
