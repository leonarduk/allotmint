import type { InstrumentPosition, InstrumentValuation } from '../types';
import { isCostBasisUnreliable } from './costBasis';
import { percent } from './money';

/** A signed percentage for a fraction (-0.16 -> "-16.0%"), or "—". */
export const signedPct = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v)
    ? '—'
    : `${v > 0 ? '+' : ''}${percent(v * 100, 1)}`;

type Nav = InstrumentValuation['nav'];

/** "2026-02-28 (218 days old)", "2026-10-03 (today)" or "unknown". */
export function navDateLabel(nav: Nav): string {
  if (!nav.as_of) return 'unknown';
  if (nav.age_days == null) return nav.as_of;
  if (nav.age_days === 0) return `${nav.as_of} (today)`;
  return `${nav.as_of} (${nav.age_days} day${nav.age_days === 1 ? '' : 's'} old)`;
}

/**
 * Why a NAV's premium/discount cannot be relied on, or null when it can.
 * A server that predates NAV status still gets "undated" for a NAV with no date.
 */
export function navUnreliability(
  nav: Nav
): { badge: string; reason: string } | null {
  const status = nav.status ?? (nav.as_of ? null : 'undated');
  const limit =
    nav.max_age_days != null ? ` (limit ${nav.max_age_days} days)` : '';
  if (status === 'stale') {
    return {
      badge: 'Stale NAV',
      reason: `Unreliable: the NAV is ${nav.age_days ?? 'too many'} days old${limit}.`,
    };
  }
  if (status === 'undated') {
    return {
      badge: 'Undated NAV',
      reason: 'Unreliable: the NAV date is unknown, so its age is too.',
    };
  }
  return null;
}

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
