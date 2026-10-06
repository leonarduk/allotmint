/**
 * Where the FX rate valuing a non-GBP holding came from (#9664): see
 * `fx_rate_source` on `Holding` (backend/common/holding_utils.py).
 */

/** Valued at an approximate hard-coded constant, not a live or cached rate. */
export const FX_RATE_SOURCE_FALLBACK = 'fallback';
/** No FX rate at all: the backend leaves the holding unpriced. */
export const FX_RATE_SOURCE_MISSING = 'missing';

/** True when the holding's FX rate is approximate or absent (#9730). */
export function isFxRateFlagged(source: string | null | undefined): boolean {
  return (
    source === FX_RATE_SOURCE_FALLBACK || source === FX_RATE_SOURCE_MISSING
  );
}
