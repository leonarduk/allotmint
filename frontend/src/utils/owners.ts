import type { OwnerSummary } from "../types";

/** Remove any placeholder/system owners that should never appear in the UI. */
export function sanitizeOwners(owners: OwnerSummary[]): OwnerSummary[] {
  const blockedOwners = new Set(["demo", ".idea"]);
  return owners.filter((owner) => !blockedOwners.has(owner.owner));
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
