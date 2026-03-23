import { money } from "@/lib/money";
import type { Transaction } from "@/types";

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
    return money(transaction.amount_minor / 100, transaction.currency ?? baseCurrency);
  }

  if (transaction.price_gbp != null && transaction.units != null) {
    return money(transaction.price_gbp * transaction.units, baseCurrency);
  }

  return "";
}

export function getTransactionRowKey(transaction: Transaction, index: number): string {
  return transaction.id ?? `${transaction.owner}-${transaction.date ?? ""}-${index}`;
}
