import type { Alert, MoverRow, Transaction } from '../types';
import { localDateISO } from './date';
import type { CurrencyAmounts } from './dividends';
import { normalizeDisplayCurrency } from './money';

/**
 * "What changed since you were last here" digest (#7835): pure helpers that
 * turn data the dashboard can already fetch (/movers, /alerts/, /dividends)
 * into a short delta since the viewer's previous visit.
 */

/**
 * A visit ends after this long without the dashboard being opened, so a
 * reload (or React StrictMode's double effect) keeps comparing against the
 * same previous visit instead of "two seconds ago".
 */
export const VISIT_SESSION_GAP_MS = 60 * 60 * 1000;

/** Windows the movers endpoints accept (backend/routes/movers.py). */
export const MOVERS_WINDOW_DAYS = [1, 7, 30, 90, 365] as const;

const DAY_MS = 24 * 60 * 60 * 1000;

/** Epoch-ms timestamps of the current visit and the one before it. */
export interface VisitRecord {
  previous: number | null;
  current: number;
}

const isTimestamp = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

/**
 * Advance the stored visit record to ``now``. Within the session gap the
 * previous visit is kept; after it, the current visit becomes the previous
 * one. A malformed record is treated as a first visit.
 */
export function advanceVisitRecord(
  record: Partial<VisitRecord> | null | undefined,
  now: number
): VisitRecord {
  if (!record || !isTimestamp(record.current)) {
    return { previous: null, current: now };
  }
  const previous = isTimestamp(record.previous) ? record.previous : null;
  if (now - record.current < VISIT_SESSION_GAP_MS) {
    return { previous, current: now };
  }
  return { previous: record.current, current: now };
}

/**
 * The record to store when the viewer dismisses the digest: everything up to
 * ``now`` counts as seen. ``previous`` is cleared so a reload within the same
 * session keeps the card hidden; once the session gap passes,
 * ``advanceVisitRecord`` rolls this visit into ``previous`` and the next card
 * only reports what changed after the dismissal.
 */
export function dismissVisitRecord(now: number): VisitRecord {
  return { previous: null, current: now };
}

/**
 * The viewer's local calendar date (YYYY-MM-DD) of ``since``. Dividend rows
 * carry local calendar dates, so comparing against the UTC date would shift
 * the boundary by a day for anyone far from UTC.
 */
export function visitDay(since: number): string {
  return localDateISO(new Date(since));
}

/** The smallest movers window that covers the time since ``since``. */
export function moversWindowDays(since: number, now: number): number {
  const elapsedDays = Math.max(1, Math.ceil((now - since) / DAY_MS));
  return (
    MOVERS_WINDOW_DAYS.find((days) => days >= elapsedDays) ??
    MOVERS_WINDOW_DAYS[MOVERS_WINDOW_DAYS.length - 1]
  );
}

export interface SinceLastVisitInput {
  /** Epoch ms of the previous visit. */
  since: number;
  /** null when the request failed, so the card can say so. */
  movers: { gainers: MoverRow[]; losers: MoverRow[] } | null;
  alerts: Alert[] | null;
  dividends: Transaction[] | null;
  /** Owner slugs in view; dividends for anyone else are ignored. */
  owners: string[];
  /**
   * Upper-cased tickers held; alerts for anything else are ignored. With no
   * holdings no alert is relevant (and /alerts/ is not owner-scoped).
   */
  heldTickers: string[];
  maxMovers?: number;
  maxAlerts?: number;
}

export interface DividendDelta {
  payments: number;
  amounts: CurrencyAmounts;
}

export interface SinceLastVisitDigest {
  movers: MoverRow[] | null;
  alerts: Alert[] | null;
  dividends: DividendDelta | null;
  /** True when every section loaded and has nothing to report. */
  nothingChanged: boolean;
}

const baseSymbol = (ticker: string): string => ticker.split('.')[0];

const isHeld = (ticker: string, held: Set<string>): boolean => {
  const upper = ticker.trim().toUpperCase();
  return held.has(upper) || held.has(baseSymbol(upper));
};

/** Biggest absolute moves first, gainers and losers together. */
export function biggestMovers(
  movers: { gainers: MoverRow[]; losers: MoverRow[] },
  limit: number
): MoverRow[] {
  return [...(movers.gainers ?? []), ...(movers.losers ?? [])]
    .filter((row) => Number.isFinite(row.change_pct))
    .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
    .slice(0, limit);
}

/**
 * Alerts raised after ``since`` for a held ticker, newest first. No held
 * tickers means no alerts: /alerts/ is not owner-scoped, so an unfiltered list
 * would show every alert in the system.
 */
export function alertsSince(
  alerts: Alert[],
  since: number,
  heldTickers: string[]
): Alert[] {
  const held = new Set(
    heldTickers.flatMap((ticker) => {
      const upper = ticker.trim().toUpperCase();
      return [upper, baseSymbol(upper)];
    })
  );
  return alerts
    .map((alert) => ({ alert, at: Date.parse(alert.timestamp) }))
    .filter(
      ({ alert, at }) =>
        Number.isFinite(at) &&
        at > since &&
        isHeld(alert.ticker ?? '', held)
    )
    .sort((a, b) => b.at - a.at)
    .map(({ alert }) => alert);
}

/**
 * Booked dividends dated on or after the viewer's local day of ``since`` for the owners in
 * view. Dividend rows carry a date only, so a payment on the day of the last
 * visit is included. Estimates and attribution-only rows are not cash paid.
 */
export function dividendsSince(
  dividends: Transaction[],
  since: number,
  owners: string[]
): DividendDelta {
  const sinceDay = visitDay(since);
  const ownerSet = new Set(owners.map((owner) => owner.toLowerCase()));
  const delta: DividendDelta = { payments: 0, amounts: {} };
  // /dividends returns every owner's rows when unscoped, so with no owner in
  // view nothing can be attributed safely (same rule as alertsSince).
  if (ownerSet.size === 0) return delta;
  for (const tx of dividends) {
    if (tx.estimated || tx.attribution_only) continue;
    if (tx.amount_minor == null || !Number.isFinite(tx.amount_minor)) continue;
    const day = tx.date?.slice(0, 10);
    if (!day || day < sinceDay) continue;
    if (!ownerSet.has((tx.owner ?? '').toLowerCase())) continue;
    const currency = normalizeDisplayCurrency(tx.currency || 'GBP');
    delta.amounts[currency] = (delta.amounts[currency] ?? 0) + tx.amount_minor / 100;
    delta.payments += 1;
  }
  return delta;
}

/** Compose the digest; a source that failed to load stays null. */
export function buildSinceLastVisitDigest({
  since,
  movers,
  alerts,
  dividends,
  owners,
  heldTickers,
  maxMovers = 3,
  maxAlerts = 5,
}: SinceLastVisitInput): SinceLastVisitDigest {
  const digest: SinceLastVisitDigest = {
    movers: movers ? biggestMovers(movers, maxMovers) : null,
    alerts: alerts ? alertsSince(alerts, since, heldTickers).slice(0, maxAlerts) : null,
    dividends: dividends ? dividendsSince(dividends, since, owners) : null,
    nothingChanged: false,
  };
  // A failed source is "unknown", not "unchanged", so the card lists it.
  digest.nothingChanged =
    digest.movers?.length === 0 &&
    digest.alerts?.length === 0 &&
    digest.dividends?.payments === 0;
  return digest;
}
