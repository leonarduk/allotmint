import type { Transaction } from "../../types";

export type TransactionFormState = {
  owner: string;
  account: string;
  date: string;
  ticker: string;
  price: string;
  units: string;
  fees: string;
  reason: string;
  comments: string;
};

export type TransactionPayload = {
  owner: string;
  account: string;
  date: string;
  ticker: string;
  price_gbp: number;
  units: number;
  reason: string;
  fees?: number;
  comments?: string;
};

export function createEmptyTransactionFormState(): TransactionFormState {
  return {
    owner: "",
    account: "",
    date: "",
    ticker: "",
    price: "",
    units: "",
    fees: "",
    reason: "",
    comments: "",
  };
}

export function createTransactionFormStateFromTransaction(
  transaction: Transaction,
): TransactionFormState {
  const ticker = (transaction.ticker ?? transaction.security_ref ?? "").toUpperCase();
  const unitsValue = transaction.units ?? transaction.shares ?? null;
  const numericUnits =
    typeof unitsValue === "number"
      ? unitsValue
      : unitsValue != null
        ? Number(unitsValue)
        : null;
  const priceValue =
    transaction.price_gbp != null
      ? transaction.price_gbp
      : transaction.amount_minor != null && numericUnits
        ? transaction.amount_minor / 100 / numericUnits
        : null;
  const legacyReason = (transaction as { reason_to_buy?: string | null }).reason_to_buy;

  return {
    owner: transaction.owner ?? "",
    account: transaction.account ?? "",
    date: transaction.date ? transaction.date.slice(0, 10) : "",
    ticker,
    price:
      priceValue != null && Number.isFinite(priceValue) ? String(priceValue) : "",
    units: numericUnits != null ? String(numericUnits) : "",
    fees: transaction.fees != null ? String(transaction.fees) : "",
    reason: transaction.reason ?? legacyReason ?? "",
    comments: transaction.comments ?? "",
  };
}

export function buildTransactionPayload(
  form: TransactionFormState,
):
  | { ok: true; payload: TransactionPayload }
  | { ok: false; error: string } {
  const price = Number.parseFloat(form.price);
  const units = Number.parseFloat(form.units);
  const fees = form.fees ? Number.parseFloat(form.fees) : undefined;
  const ticker = form.ticker.trim().toUpperCase();
  const reason = form.reason.trim();
  const comments = form.comments.trim();

  if (!form.owner || !form.account || !form.date || !ticker || !reason) {
    return { ok: false, error: "Please complete all required fields." };
  }
  if (!Number.isFinite(price) || price <= 0) {
    return { ok: false, error: "Enter a valid price." };
  }
  if (!Number.isFinite(units) || units <= 0) {
    return { ok: false, error: "Enter a valid number of units." };
  }
  if (form.fees && (fees == null || Number.isNaN(fees))) {
    return { ok: false, error: "Enter a valid fee or leave it blank." };
  }
  if (fees != null && fees < 0) {
    return { ok: false, error: "Fees cannot be negative." };
  }

  return {
    ok: true,
    payload: {
      owner: form.owner,
      account: form.account,
      date: form.date,
      ticker,
      price_gbp: price,
      units,
      reason,
      fees,
      comments: comments || undefined,
    },
  };
}

export function paginateTransactions(
  transactions: Transaction[] | null | undefined,
  currentPage: number,
  pageSize: number,
): Transaction[] {
  if (!transactions?.length) {
    return [];
  }
  const startIndex = currentPage * pageSize;
  return transactions.slice(startIndex, startIndex + pageSize);
}

export function buildShowingRangeLabel(
  totalTransactions: number,
  currentPage: number,
  pageSize: number,
): string {
  if (totalTransactions === 0) {
    return "Showing 0 of 0";
  }
  const pageStart = currentPage * pageSize + 1;
  const pageEnd = Math.min(totalTransactions, (currentPage + 1) * pageSize);
  return `Showing ${pageStart}-${pageEnd} of ${totalTransactions}`;
}
