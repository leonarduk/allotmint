export function formatDateISO(date: Date): string {
  return date.toISOString().split('T')[0];
}

const RELATIVE_UNITS: Array<{ limit: number; unit: Intl.RelativeTimeFormatUnit; secs: number }> = [
  { limit: 60, unit: 'second', secs: 1 },
  { limit: 3600, unit: 'minute', secs: 60 },
  { limit: 86400, unit: 'hour', secs: 3600 },
  { limit: 604800, unit: 'day', secs: 86400 },
  { limit: 2629800, unit: 'week', secs: 604800 },
  { limit: 31557600, unit: 'month', secs: 2629800 },
  { limit: Infinity, unit: 'year', secs: 31557600 },
];

/**
 * Format an ISO-8601 timestamp as a short human-friendly age, e.g. "3 days ago".
 *
 * Returns ``null`` when the value is missing or cannot be parsed, so callers can
 * decide whether to render anything at all.
 */
export function formatPublishedAt(value: string | null | undefined, now: Date = new Date()): string | null {
  if (!value) {
    return null;
  }
  const published = new Date(value);
  const ms = published.getTime();
  if (Number.isNaN(ms)) {
    return null;
  }

  const diffSecs = Math.round((ms - now.getTime()) / 1000);
  const absSecs = Math.abs(diffSecs);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  for (const { limit, unit, secs } of RELATIVE_UNITS) {
    if (absSecs < limit) {
      return rtf.format(Math.round(diffSecs / secs), unit);
    }
  }
  return rtf.format(Math.round(diffSecs / 31557600), 'year');
}
