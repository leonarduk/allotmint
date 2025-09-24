import type { OwnerSummary } from "../types";

/**
 * Filter out demo owners when real owners exist, but preserve the demo owner when
 * it is the only option (e.g. demo mode environments).
 */
export function sanitizeOwners(owners: OwnerSummary[]): OwnerSummary[] {
  const nonDemoOwners = owners.filter((owner) => owner.owner !== "demo");
  return nonDemoOwners.length > 0 ? nonDemoOwners : owners;
}
