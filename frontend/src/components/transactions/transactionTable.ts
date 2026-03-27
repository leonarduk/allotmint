import { money } from "@/lib/money";
import type { Transaction } from "@/types";

/**
 * Orders IDs for bulk deletion so that higher-index entries within the same
 * owner:account group are deleted first. This prevents index-shift bugs on the
 * backend when records are stored as positional arrays.
 *
 * Expected ID format: "<owner>:<account>:<index>" (e.g. "alex:isa:3").
 * IDs that do not match this format (e.g. UUIDs, legacy opaque IDs) are placed
 * at the end of the deletion list in their original order via fallbackIds.
 */
export function buildBulkDeletionOrder(selectedIds: string[]): string[] {
  const groupedIds = new Map<string, { entries: { id: string; index: number }[] }>();
  const fallbackIds: string[] = [];

  selectedIds.forEach((id) => {
    const [ownerPart, accountPart, indexPart] = id.split(":");
    const parsedIndex = Number.parseInt(indexPart ?? "", 10);

    if (!ownerPart || !accountPart || Number.isNaN(parsedIndex)) {
      fallbackIds.push(id);
      return;
    }

    const key = `${ownerPart}:${accountPart}`;
    const group = groupedIds.get(key) ?? { entries: [] };
    group.entries.push({ id, index: parsedIndex });
    groupedIds.set(key, group);
  });

  const deletionOrder: string[] = [];

  groupedIds.forEach((group) => {
    group.entries
      .sort((a, b) => b.index - a.index)
      .forEach(({ id }) => {
        deletionOrder.push(id);
      });
  });

  deletionOrder.push(...fallbackIds);
  return deletionOrder;
}

export function formatTransactionAmount(
  transaction: Transaction,
  baseCurrency: string,
): string {
  if (transaction.amount_minor != null) {
    // Use || rather than ?? so that an empty string currency also falls back
    // to baseCurrency (the backend should never send "", but guard defensively).
    return money(transaction.amount_minor / 100, transaction.currency || baseCurrency);
  }

  if (transaction.price_gbp != null && transaction.units != null) {
    return money(transaction.price_gbp * transaction.units, baseCurrency);
  }

  if (transaction.price_gbp != null && transaction.shares != null) {
    return money(transaction.price_gbp * transaction.shares, baseCurrency);
  }

  return "";
}

export function getTransactionRowKey(transaction: Transaction, index: number): string {
  return transaction.id ?? `${transaction.owner}-${transaction.date ?? ""}-${index}`;
}
