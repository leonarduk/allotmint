import type { OwnerSummary } from "../types";

/** Remove any placeholder/system owners that should never appear in the UI. */
export function sanitizeOwners(owners: OwnerSummary[]): OwnerSummary[] {
  const blockedOwners = new Set(["demo", ".idea"]);
  return owners.filter((owner) => !blockedOwners.has(owner.owner));
}
