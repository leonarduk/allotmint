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
