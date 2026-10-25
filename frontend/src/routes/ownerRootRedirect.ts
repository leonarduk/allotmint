import type { UserProfile } from '../AuthContext';
import type { GroupSummary, OwnerSummary } from '../types';
import { findOwnerForUser } from '../utils/owners';
import { DEFAULT_GROUP_SLUG } from '../utils/groups';
import { encodePathSegment } from '../utils/urlUtils';
import { readRouteScopeQuery } from './registry';

/**
 * Where a bare `/performance` (no owner segment, no `?group=`) should land.
 *
 * Performance defaults to the household group view, like the group-first
 * Dashboard (#7214): `preferredGroup` (the group the Dashboard is on) when it
 * is one of `groups`, else "all", else the first group. Only when there are no
 * groups does it fall back to an owner -- the signed-in user's own, else the
 * first. `groups` is null while /groups is still loading; the result is then
 * null, so the page never lands on an owner just because owners loaded first.
 */
export function getPerformanceRootRedirectPath(
  owners: OwnerSummary[],
  groups: GroupSummary[] | null,
  user?: UserProfile | null,
  preferredGroup?: string | null
): string | null {
  if (groups === null) return null;
  if (groups.length > 0) {
    const slugs = groups.map((group) => group.slug);
    const slug =
      preferredGroup && slugs.includes(preferredGroup)
        ? preferredGroup
        : slugs.includes(DEFAULT_GROUP_SLUG)
          ? DEFAULT_GROUP_SLUG
          : slugs[0];
    return `/performance?group=${encodeURIComponent(slug)}`;
  }
  if (owners.length === 0) return null;
  const owner = findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
  return `/performance/${encodePathSegment(owner)}`;
}

// Lives outside App.tsx so tests of this pure helper don't have to load (and,
// on a cold cache, transform) App's whole eager module graph (#10720).
//
// `groups` only affects the performance root (see
// getPerformanceRootRedirectPath); when omitted it is treated as an empty
// list, so the performance root falls back to an owner.
export function getOwnerRootRedirectPath(
  pathname: string,
  selectedOwner: string,
  owners: OwnerSummary[],
  user?: UserProfile | null,
  search = '',
  groups: GroupSummary[] | null = [],
  preferredGroup?: string | null
): string | null {
  if (selectedOwner || owners.length === 0) return null;
  const segs = pathname.split('/').filter(Boolean);
  const atPortfolioRoot = segs[0] === 'portfolio' && segs.length === 1;
  const atPerformanceRoot = segs[0] === 'performance' && segs.length === 1;
  if (!atPortfolioRoot && !atPerformanceRoot) return null;
  // A bare `/performance?group=<slug>` is a deliberate group-scope landing
  // (#7228), not an unscoped root that should be forced onto an owner.
  if (atPerformanceRoot && readRouteScopeQuery(search).group) return null;
  if (atPerformanceRoot) {
    return getPerformanceRootRedirectPath(owners, groups, user, preferredGroup);
  }
  const owner = findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
  return `/portfolio/${encodePathSegment(owner)}`;
}
