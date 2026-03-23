import type { Transaction } from "@/types";

export type TransactionFormValues = {
  owner: string;
  account: string;
  date: string;
  ticker: string;
  price: string;
  units: string;
  fees: string;
  comments: string;
  reason: string;
};

export const EMPTY_TRANSACTION_FORM_VALUES: TransactionFormValues = {
  owner: "",
  account: "",
  date: "",
  ticker: "",
  price: "",
  units: "",
  fees: "",
  comments: "",
  reason: "",
};

export function createTransactionFormValues(
  transaction?: Transaction | null,
): TransactionFormValues {
  if (!transaction) {
    return { ...EMPTY_TRANSACTION_FORM_VALUES };
  }

  const tickerValue = (
    transaction.ticker ?? transaction.security_ref ?? ""
  ).toUpperCase();
  const unitsValue = transaction.units ?? transaction.shares ?? null;
  const numericUnits =
    typeof unitsValue === "number"
      ? unitsValue
      : unitsValue != null
        ? Number(unitsValue)
        : null;

  // Prefer explicit price_gbp. When deriving from amount_minor, round to 2dp
  // to avoid floating-point precision loss (e.g. 1000 minor / 100 / 3 = 3.333...).
  // An unrounded value would silently mutate price_gbp on every edit round-trip.
  const rawDerivedPrice =
    transaction.amount_minor != null && numericUnits
      ? transaction.amount_minor / 100 / numericUnits
      : null;
  const priceValue =
    transaction.price_gbp != null
      ? transaction.price_gbp
      : rawDerivedPrice != null
        ? Math.round(rawDerivedPrice * 100) / 100
        : null;

  const legacyReason = (transaction as { reason_to_buy?: string | null }).reason_to_buy;

  return {
    owner: transaction.owner,
    account: transaction.account,
    date: transaction.date ? transaction.date.slice(0, 10) : "",
    ticker: tickerValue,
    price:
      priceValue != null && Number.isFinite(priceValue) ? String(priceValue) : "",
    units: numericUnits != null ? String(numericUnits) : "",
    fees: transaction.fees != null ? String(transaction.fees) : "",
    comments: transaction.comments ?? "",
    reason: transaction.reason ?? legacyReason ?? "",
  };
}

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

export type BuildTransactionPayloadResult =
  | { payload: TransactionPayload; error: null }
  | { payload: null; error: string };

export function buildTransactionPayload(
  values: TransactionFormValues,
): BuildTransactionPayloadResult {
  const price = Number.parseFloat(values.price);
  const units = Number.parseFloat(values.units);
  const fees = values.fees ? Number.parseFloat(values.fees) : undefined;
  const ticker = values.ticker.trim().toUpperCase();
  const reason = values.reason.trim();
  const comments = values.comments.trim();

  if (!values.owner || !values.account || !values.date || !ticker || !reason) {
    return {
      payload: null,
      error: "Please complete all required fields.",
    };
  }

  if (!Number.isFinite(price) || price <= 0) {
    return { payload: null, error: "Enter a valid price." };
  }

  if (!Number.isFinite(units) || units <= 0) {
    return { payload: null, error: "Enter a valid number of units." };
  }

  if (values.fees && (fees == null || Number.isNaN(fees))) {
    return { payload: null, error: "Enter a valid fee or leave it blank." };
  }

  if (fees != null && fees < 0) {
    return { payload: null, error: "Fees cannot be negative." };
  }

  return {
    payload: {
      owner: values.owner,
      account: values.account,
      date: values.date,
      ticker,
      price_gbp: price,
      units,
      reason,
      fees,
      comments: comments || undefined,
    },
    error: null,
  };
}
