import { useEffect, useMemo, useState } from 'react';
import { getGroups } from '../api';
import type { GroupSummary, OwnerSummary } from '../types';

/**
 * Filters `owners` down to whoever actually belongs to a configured group
 * (the real household), for the grower *picker* to render.
 *
 * `/groups` defines the real household membership (e.g. "adults",
 * "children"); it is what keeps accounts with no household membership —
 * notably the demo/seed account — out of the grower picker. This is
 * deliberately a separate, non-fatal fetch from owner discovery: a failed or
 * empty `/groups` response must not surface an error, it should just leave
 * `groups` empty and let `pickerOwners` fall back to showing every owner
 * (#7189).
 *
 * `groupsStatus` mirrors the owner-discovery status for the same reason: an
 * empty `groups` array is ambiguous between "not loaded yet" and "loaded, no
 * groups configured" and only one of those should make `pickerOwners` fall
 * back to the unfiltered list. Without this, `pickerOwners` briefly equals
 * the full `owners` list (demo account included) the instant `/owners`
 * resolves, then narrows a moment later once `/groups` catches up — the
 * exact "wrong grower's data flashes on screen" class of bug
 * `clearOwnerScopedState` exists to prevent elsewhere in `PlotDataContext`.
 *
 * While `/groups` is still in flight this deliberately returns an empty list
 * rather than the unfiltered `owners`, so the picker (which also hides itself
 * below two options) simply stays hidden for that brief window instead of
 * showing every account and then narrowing. `owners` itself is left
 * untouched for the data layer — deep links like `?owner=demo` bypass this
 * list entirely and keep working via the `requestedOwner` effect in
 * `PlotDataContext` (#7189, #7192).
 */
export function useGroupedOwners(
  owners: OwnerSummary[],
  reloadToken: number
): OwnerSummary[] {
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [groupsStatus, setGroupsStatus] = useState<
    'pending' | 'ready' | 'error'
  >('pending');

  useEffect(() => {
    let cancelled = false;
    setGroupsStatus('pending');
    getGroups()
      .then((list) => {
        if (cancelled) return;
        setGroups(list);
        setGroupsStatus('ready');
      })
      .catch(() => {
        // Swallowed deliberately: `groups` just stays empty and `ready`'s
        // "no grouping configured" fallback below applies equally to a
        // genuinely-empty response and a failed one.
        if (cancelled) return;
        setGroups([]);
        setGroupsStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // The set of owner slugs that belong to at least one group. Membership,
  // not an exclusion list, is the rule — this is why the demo account (which
  // simply isn't in any group) drops out without `"demo"` ever being named
  // in this file (#7189).
  const groupedOwnerSlugs = useMemo(() => {
    const slugs = new Set<string>();
    for (const group of groups) {
      for (const member of group.members) slugs.add(member);
    }
    return slugs;
  }, [groups]);

  // The picker's option list: real owners only, with a fall back to the full
  // `owners` list whenever grouping data can't narrow it down (`/groups`
  // failed, or none of the current owners matched any group).
  return useMemo(() => {
    if (groupsStatus === 'pending') return [];
    if (groupedOwnerSlugs.size === 0) return owners;
    const filtered = owners.filter((entry) =>
      groupedOwnerSlugs.has(entry.owner)
    );
    return filtered.length > 0 ? filtered : owners;
  }, [owners, groupedOwnerSlugs, groupsStatus]);
}
