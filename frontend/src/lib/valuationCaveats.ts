import type { InstrumentPosition, InstrumentValuation } from '../types';
import { isCostBasisUnreliable } from './costBasis';
import { percent } from './money';

/** A signed percentage for a fraction (-0.16 -> "-16.0%"), or "—". */
export const signedPct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v)
    ? '—'
    : `${v > 0 ? '+' : ''}${percent(v * 100, 1)}`;

/** Data-quality caveats, collected so they show above the numbers they qualify. */
export function valuationCaveats(
  profile: InstrumentValuation | null,
  positions: InstrumentPosition[]
): string[] {
  const caveats: string[] = [];
  const snapshot = profile?.data_quality.price_snapshot;
  if (snapshot?.is_stale) {
    caveats.push(
      `Latest price is flagged stale${snapshot.last_price_date ? ` (as of ${snapshot.last_price_date})` : ''}.`
    );
  }
  const suspect = positions.filter((p) =>
    isCostBasisUnreliable(p.cost_basis_source)
  );
  if (suspect.length > 0) {
    const where = suspect.map((p) => `${p.owner}/${p.account}`).join(', ');
    caveats.push(
      `Cost basis is suspect or unknown for ${suspect.length} position(s): ${where}.`
    );
  }
  for (const move of profile?.data_quality.suspect_moves ?? []) {
    caveats.push(
      `Suspect one-day move of ${signedPct(move.change)} on ${move.date}.`
    );
  }
  caveats.push(...(profile?.data_quality.warnings ?? []));
  return caveats;
}
