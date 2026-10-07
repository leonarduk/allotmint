// Shared sign colours (#7817): the index and sector charts must never
// disagree about which way is up.
export const POSITIVE_COLOR = '#16a34a';
export const NEGATIVE_COLOR = '#dc2626';

export const changeColor = (change: number | null | undefined) =>
  (change ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;

export const formatPctTick = (value: unknown) => `${Number(value).toFixed(1)}%`;

// Index levels always show two decimals: the default toLocaleString keeps up
// to three, so one column mixed 7,650.5 with 26,522.545 (#7788).
export const formatIndexLevel = (value: number) =>
  value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

/**
 * The most recent `as_of` across the indexes, formatted for display, or null
 * when none carries one. A bare date (a period's last close) shows as a date;
 * a timestamped live quote also shows its time.
 */
export const formatLatestAsOf = (
  indexes: Record<string, { as_of?: string }>,
): string | null => {
  const stamps = Object.values(indexes)
    .map((row) => row.as_of)
    .filter((s): s is string => typeof s === 'string')
    .filter((s) => !Number.isNaN(Date.parse(s)));
  if (stamps.length === 0) return null;
  const latest = stamps.reduce((a, b) => (Date.parse(b) > Date.parse(a) ? b : a));
  const hasZone = /(Z|[+-]\d{2}:\d{2})$/.test(latest);
  return new Date(latest).toLocaleString(
    undefined,
    hasZone ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' },
  );
};
