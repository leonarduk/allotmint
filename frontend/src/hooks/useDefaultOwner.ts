import { useAuth } from '../AuthContext';
import type { OwnerSummary } from '../types';
import { pickDefaultOwner } from '../utils/owners';

/**
 * The owner an owner-scoped page should open on: `preferred` (route or
 * `?owner=`) when valid, else the signed-in user's owner, else owners[0].
 * See pickDefaultOwner (#10753).
 */
export function useDefaultOwner(
  owners: OwnerSummary[],
  preferred?: string | null
): string {
  const { user } = useAuth();
  return pickDefaultOwner(owners, user, preferred);
}
