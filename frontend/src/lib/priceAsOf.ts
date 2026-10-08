import type { TFunction } from 'i18next';

import type { LiveQuote } from '../api';
import { localDateISO } from './date';

/** Whether a displayed price is a real-time quote, a delayed one, or a close. */
export type PriceAsOfKind = 'live' | 'delayed' | 'close';

export type PriceAsOf = {
  kind: PriceAsOfKind;
  /** Short badge text, e.g. "Live 14:31", "Delayed 14:16", "Close 2026-10-06". */
  label: string;
  /** Full timestamp/date for a tooltip. */
  title: string;
};

const clock = (d: Date) =>
  d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** HH:MM for today, otherwise "YYYY-MM-DD HH:MM" (both in local time). */
const timeLabel = (d: Date) => {
  const day = localDateISO(d);
  return day === localDateISO() ? clock(d) : `${day} ${clock(d)}`;
};

/**
 * As-of label for a live quote. During the regular session it is a real-time
 * (or, if over 15 minutes old, delayed) price; outside it (pre/post market or
 * closed) Yahoo's regular-market price is that session's close, so it is
 * labelled as the close of the quote's trading day.
 */
export function liveQuoteAsOf(quote: LiveQuote, t: TFunction): PriceAsOf {
  const quoted = new Date(quote.timestamp);
  const outsideSession =
    quote.market_state != null && quote.market_state !== 'REGULAR';
  if (outsideSession) {
    return {
      kind: 'close',
      label: t('priceAsOf.close', { date: localDateISO(quoted) }),
      title: quote.timestamp,
    };
  }
  const kind: PriceAsOfKind = quote.is_stale ? 'delayed' : 'live';
  return {
    kind,
    label: t(`priceAsOf.${kind}`, { time: timeLabel(quoted) }),
    title: quote.timestamp,
  };
}

/** As-of label for a stored close-of-business price dated `date` (YYYY-MM-DD). */
export function closeAsOf(
  date: string | null | undefined,
  t: TFunction
): PriceAsOf | null {
  if (!date) return null;
  const day = date.slice(0, 10);
  return {
    kind: 'close',
    label: t('priceAsOf.close', { date: day }),
    title: date,
  };
}
