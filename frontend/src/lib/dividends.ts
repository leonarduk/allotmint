import type { Account, Transaction } from '../types';
import { isCashInstrument } from './instruments';
import { normalizeDisplayCurrency } from './money';

/** Amounts in major units keyed by currency: never summed across currencies (#9805). */
export type CurrencyAmounts = Record<string, number>;

export type DividendPeriod = 'taxYear' | 'year' | 'month';

export interface DividendPeriodRow {
  period: string;
  amounts: CurrencyAmounts;
  payments: number;
}

export interface DividendHoldingRow {
  /** Upper-cased ticker, or null for payments not linked to a holding. */
  ticker: string | null;
  name: string | null;
  /** Dividend rows recorded. 0 means no history -- not "paid nothing". */
  payments: number;
  lastPaid: string | null;
  total: CurrencyAmounts;
  trailing12m: CurrencyAmounts;
}

export interface DividendSummary {
  total: CurrencyAmounts;
  trailing12m: CurrencyAmounts;
  periods: DividendPeriodRow[];
  holdings: DividendHoldingRow[];
  payments: number;
}

interface Payment {
  date: Date | null;
  dateText: string | null;
  ticker: string | null;
  name: string | null;
  currency: string;
  amount: number;
}

const add = (target: CurrencyAmounts, currency: string, amount: number) => {
  target[currency] = (target[currency] ?? 0) + amount;
};

const parseDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const toPayment = (tx: Transaction): Payment | null => {
  if (tx.amount_minor == null || !Number.isFinite(tx.amount_minor)) return null;
  const ticker = tx.ticker?.trim().toUpperCase() || null;
  return {
    date: parseDate(tx.date),
    dateText: tx.date ? tx.date.slice(0, 10) : null,
    ticker,
    name: tx.instrument_name ?? null,
    currency: normalizeDisplayCurrency(tx.currency || 'GBP'),
    amount: tx.amount_minor / 100,
  };
};

/** The period label a payment date falls into; UK tax years run 6 April to 5 April. */
export function periodLabel(date: Date, period: DividendPeriod): string {
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  if (period === 'month') return `${year}-${String(month).padStart(2, '0')}`;
  if (period === 'year') return String(year);
  const startsNewTaxYear = month > 4 || (month === 4 && date.getUTCDate() >= 6);
  const start = startsNewTaxYear ? year : year - 1;
  return `${start}/${String((start + 1) % 100).padStart(2, '0')}`;
}

const trailingCutoff = (now: Date): Date => {
  const cutoff = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
  return cutoff;
};

/**
 * Distinct current holdings by upper-cased ticker, keeping the first name
 * seen. Cash positions never pay dividends, so they are left out.
 */
export function holdingsFromAccounts(
  accounts: Account[]
): Map<string, string | null> {
  const held = new Map<string, string | null>();
  for (const account of accounts) {
    for (const holding of account.holdings ?? []) {
      const ticker = holding.ticker?.trim().toUpperCase();
      if (
        !ticker ||
        isCashInstrument({ ticker, instrument_type: holding.instrument_type })
      )
        continue;
      if (!held.has(ticker)) held.set(ticker, holding.name || null);
    }
  }
  return held;
}

const emptyHoldingRow = (
  ticker: string | null,
  name: string | null
): DividendHoldingRow => ({
  ticker,
  name,
  payments: 0,
  lastPaid: null,
  total: {},
  trailing12m: {},
});

const sortHoldings = (rows: DividendHoldingRow[]) =>
  rows.sort((a, b) => {
    // Paying holdings first, then unattributed, then holdings with no history.
    const rank = (r: DividendHoldingRow) =>
      r.payments === 0 ? 2 : r.ticker ? 0 : 1;
    return rank(a) - rank(b) || (a.ticker ?? '').localeCompare(b.ticker ?? '');
  });

/**
 * Summarise dividend transactions by period and by holding. Current holdings
 * with no dividend rows are listed with `payments: 0` so the page can say
 * "no dividends recorded" instead of showing a misleading zero amount.
 */
export function summariseDividends(
  transactions: Transaction[],
  options: {
    period: DividendPeriod;
    now?: Date;
    holdings?: Map<string, string | null>;
  }
): DividendSummary {
  const cutoff = trailingCutoff(options.now ?? new Date());
  const total: CurrencyAmounts = {};
  const trailing12m: CurrencyAmounts = {};
  const periods = new Map<string, DividendPeriodRow>();
  const holdings = new Map<string, DividendHoldingRow>();
  let payments = 0;

  for (const tx of transactions) {
    const payment = toPayment(tx);
    if (!payment) continue;
    payments += 1;
    const inTrailing = payment.date !== null && payment.date > cutoff;
    add(total, payment.currency, payment.amount);
    if (inTrailing) add(trailing12m, payment.currency, payment.amount);

    const label = payment.date ? periodLabel(payment.date, options.period) : '';
    const periodRow = periods.get(label) ?? {
      period: label,
      amounts: {},
      payments: 0,
    };
    add(periodRow.amounts, payment.currency, payment.amount);
    periodRow.payments += 1;
    periods.set(label, periodRow);

    const key = payment.ticker ?? '';
    const row =
      holdings.get(key) ?? emptyHoldingRow(payment.ticker, payment.name);
    row.payments += 1;
    row.name = row.name ?? payment.name;
    add(row.total, payment.currency, payment.amount);
    if (inTrailing) add(row.trailing12m, payment.currency, payment.amount);
    if (
      payment.dateText &&
      (!row.lastPaid || payment.dateText > row.lastPaid)
    ) {
      row.lastPaid = payment.dateText;
    }
    holdings.set(key, row);
  }

  for (const [ticker, name] of options.holdings ?? []) {
    const existing = holdings.get(ticker);
    if (existing) existing.name = existing.name ?? name;
    else holdings.set(ticker, emptyHoldingRow(ticker, name));
  }

  // Newest period first; undated payments ("") sort last.
  const periodRows = [...periods.values()].sort((a, b) =>
    a.period === ''
      ? 1
      : b.period === ''
        ? -1
        : b.period.localeCompare(a.period)
  );

  return {
    total,
    trailing12m,
    periods: periodRows,
    holdings: sortHoldings([...holdings.values()]),
    payments,
  };
}
