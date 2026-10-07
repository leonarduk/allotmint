import type { Account } from "../types";
import { getOwnerDisplayName } from "../utils/owners";

export type OwnerTab = { value: string; label: string; accountTypes: string[] };

/** One tab per distinct account owner, in first-seen order, with that owner's account types. */
export function buildOwnerTabs(
  accounts: Account[] | undefined,
  ownerLookup: Map<string, string>,
): OwnerTab[] {
  const index = new Map<string, { value: string; label: string; accountTypes: Set<string> }>();
  for (const acct of accounts ?? []) {
    if (!acct.owner) continue;
    let entry = index.get(acct.owner);
    if (!entry) {
      entry = {
        value: acct.owner,
        label: getOwnerDisplayName(ownerLookup, acct.owner, acct.owner),
        accountTypes: new Set<string>(),
      };
      index.set(acct.owner, entry);
    }
    entry.accountTypes.add(acct.account_type);
  }
  return Array.from(index.values(), ({ value, label, accountTypes }) => ({
    value,
    label,
    accountTypes: Array.from(accountTypes),
  }));
}
