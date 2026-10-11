import type { UserProfile } from '../AuthContext';
import type { OwnerSummary } from '../types';
import { findOwnerForUser } from '../utils/owners';
import { encodePathSegment } from '../utils/urlUtils';
import { readRouteScopeQuery } from './registry';

// Lives outside App.tsx so tests of this pure helper don't have to load (and,
// on a cold cache, transform) App's whole eager module graph (#10720).
export function getOwnerRootRedirectPath(
  pathname: string,
  selectedOwner: string,
  owners: OwnerSummary[],
  user?: UserProfile | null,
  search = ''
): string | null {
  if (selectedOwner || owners.length === 0) return null;
  const segs = pathname.split('/').filter(Boolean);
  const atPortfolioRoot = segs[0] === 'portfolio' && segs.length === 1;
  const atPerformanceRoot = segs[0] === 'performance' && segs.length === 1;
  if (!atPortfolioRoot && !atPerformanceRoot) return null;
  // A bare `/performance?group=<slug>` is a deliberate group-scope landing
  // (#7228), not an unscoped root that should be forced onto an owner.
  if (atPerformanceRoot && readRouteScopeQuery(search).group) return null;
  const owner = findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
  const encodedOwner = encodePathSegment(owner);
  return atPerformanceRoot
    ? `/performance/${encodedOwner}`
    : `/portfolio/${encodedOwner}`;
}
