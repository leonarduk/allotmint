import type { OwnerSummary } from "../types";

/** Remove any placeholder/system owners that should never appear in the UI. */
export function sanitizeOwners(owners: OwnerSummary[]): OwnerSummary[] {
  const blockedOwners = new Set(["demo", ".idea"]);
  const filtered = owners.filter((owner) => !blockedOwners.has(owner.owner));

  if (filtered.length > 0) {
    return filtered;
  }

  // When every owner is filtered out we still want to expose demo accounts so that
  // local/test environments retain at least one selectable owner. System-only
  // placeholders such as ``.idea`` should continue to be hidden.
  return owners.filter((owner) => owner.owner !== ".idea");
}

export function createOwnerDisplayLookup(
  owners: OwnerSummary[],
): Map<string, string> {
  const lookup = new Map<string, string>();
  owners.forEach(({ owner, full_name }) => {
    if (!owner) return;
    const display = full_name?.trim();
    lookup.set(owner, display && display.length > 0 ? display : owner);
  });
  return lookup;
}

export function getOwnerDisplayName(
  lookup: Map<string, string>,
  owner: string | null | undefined,
  fallback?: string,
): string {
  if (!owner) {
    return fallback ?? "—";
  }
  return lookup.get(owner) ?? fallback ?? owner;
}

/**
 * Map a logged-in user to one of the available owners by email, so the app
 * defaults to the current user's own owner rather than an arbitrary one.
 * Returns undefined when there's no auth user or no matching owner (e.g.
 * demo/local/no-auth mode), in which case callers should fall back to
 * owners[0].
 */
export function findOwnerForUser(
  owners: OwnerSummary[],
  user: { email?: string | null } | null | undefined,
): OwnerSummary | undefined {
  const email = user?.email?.trim().toLowerCase();
  if (!email) return undefined;
  return owners.find((owner) => owner.email?.trim().toLowerCase() === email);
}
