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
  const price =
    typeof transaction.price_gbp === "number" && Number.isFinite(transaction.price_gbp)
      ? transaction.price_gbp
      : null;
  const units =
    typeof transaction.units === "number" && Number.isFinite(transaction.units)
      ? transaction.units
      : null;
  const shares =
    typeof transaction.shares === "number" && Number.isFinite(transaction.shares)
      ? transaction.shares
      : null;

  if (transaction.amount_minor != null) {
    // Use || rather than ?? so that an empty string currency also falls back
    // to baseCurrency (the backend should never send "", but guard defensively).
    return money(transaction.amount_minor / 100, transaction.currency || baseCurrency);
  }

  if (price == null) {
    return "";
  }

  if (units != null && shares != null) {
    console.warn(
      "Transaction contains both units and shares; using units for amount display.",
      transaction,
    );
    return money(price * units, baseCurrency);
  }

  if (units != null) {
    return money(price * units, baseCurrency);
  }

  if (shares != null) {
    return money(price * shares, baseCurrency);
  }

  return "";
}

export function getTransactionRowKey(transaction: Transaction, index: number): string {
  return transaction.id ?? `${transaction.owner}-${transaction.date ?? ""}-${index}`;
}

export interface RealisedGainCell {
  text: string;
  className: string;
  title?: string;
}

export function formatRealisedGain(
  transaction: Transaction,
  baseCurrency: string,
): RealisedGainCell {
  const gain = transaction.realised_gain_gbp;
  if (typeof gain === "number" && Number.isFinite(gain)) {
    const cost = transaction.cost_basis_gbp;
    return {
      text: money(gain, baseCurrency),
      className: gain > 0 ? "text-positive" : gain < 0 ? "text-negative" : "text-gray",
      title:
        typeof cost === "number" ? `Cost basis ${money(cost, baseCurrency)}` : undefined,
    };
  }
  const unmatched = transaction.unmatched_units;
  if (typeof unmatched === "number" && unmatched > 0) {
    return {
      text: "Unknown",
      className: "text-gray",
      title: `No purchase cost recorded for ${unmatched} of the units sold`,
    };
  }
  return { text: "", className: "" };
}

const INCOME_TYPES = new Set(["DIVIDEND", "DIVIDENDS", "INTEREST"]);

export interface TransactionsSummary {
  realisedGain: number;
  sellsWithUnknownGain: number;
  income: number;
  fees: number;
}

/** Totals over the given rows; cash amounts come from `amount_minor` (pence). */
export function summariseTransactions(transactions: Transaction[]): TransactionsSummary {
  const summary: TransactionsSummary = {
    realisedGain: 0,
    sellsWithUnknownGain: 0,
    income: 0,
    fees: 0,
  };
  transactions.forEach((tx) => {
    const type = (tx.type ?? "").toUpperCase();
    const amount =
      typeof tx.amount_minor === "number" && Number.isFinite(tx.amount_minor)
        ? Math.abs(tx.amount_minor) / 100
        : 0;
    if (typeof tx.realised_gain_gbp === "number" && Number.isFinite(tx.realised_gain_gbp)) {
      summary.realisedGain += tx.realised_gain_gbp;
    } else if (type === "SELL" && (tx.unmatched_units ?? 0) > 0) {
      summary.sellsWithUnknownGain += 1;
    }
    if (INCOME_TYPES.has(type)) summary.income += amount;
    if (type === "FEES") summary.fees += amount;
    if (type === "FEES_REFUND") summary.fees -= amount;
  });
  return summary;
}
