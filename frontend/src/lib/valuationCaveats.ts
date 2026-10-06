import i18n from '../i18n';
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
  if (!nav.as_of) return i18n.t('valuationCaveats.navUnknown');
  if (nav.age_days == null) return nav.as_of;
  if (nav.age_days === 0)
    return i18n.t('valuationCaveats.navToday', { date: nav.as_of });
  return i18n.t('valuationCaveats.navAge', {
    date: nav.as_of,
    count: nav.age_days,
  });
}

/**
 * Why a NAV's premium/discount cannot be relied on, or null when it can.
 * A server that predates NAV status still gets "undated" for a NAV with no date.
 */
export function navUnreliability(
  nav: Nav
): { badge: string; reason: string } | null {
  const status = nav.status ?? (nav.as_of ? null : 'undated');
  if (status === 'stale') {
    const age = nav.age_days ?? i18n.t('valuationCaveats.tooManyDays');
    return {
      badge: i18n.t('valuationCaveats.staleBadge'),
      reason:
        nav.max_age_days != null
          ? i18n.t('valuationCaveats.staleReasonLimit', {
              age,
              limit: nav.max_age_days,
            })
          : i18n.t('valuationCaveats.staleReason', { age }),
    };
  }
  if (status === 'undated') {
    return {
      badge: i18n.t('valuationCaveats.undatedBadge'),
      reason: i18n.t('valuationCaveats.undatedReason'),
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
      snapshot.last_price_date
        ? i18n.t('valuationCaveats.stalePriceAsOf', {
            date: snapshot.last_price_date,
          })
        : i18n.t('valuationCaveats.stalePrice')
    );
  }
  const suspect = positions.filter((p) =>
    isCostBasisUnreliable(p.cost_basis_source)
  );
  if (suspect.length > 0) {
    const where = suspect.map((p) => `${p.owner}/${p.account}`).join(', ');
    caveats.push(
      i18n.t('valuationCaveats.suspectCostBasis', {
        count: suspect.length,
        where,
      })
    );
  }
  for (const move of profile?.data_quality.suspect_moves ?? []) {
    caveats.push(
      i18n.t('valuationCaveats.suspectMove', {
        change: signedPct(move.change),
        date: move.date,
      })
    );
  }
  caveats.push(...(profile?.data_quality.warnings ?? []));
  return caveats;
}
