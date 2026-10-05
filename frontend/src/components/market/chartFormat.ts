// Shared sign colours (#7817): the index and sector charts must never
// disagree about which way is up.
export const POSITIVE_COLOR = '#16a34a';
export const NEGATIVE_COLOR = '#dc2626';

export const changeColor = (change: number | null | undefined) =>
  (change ?? 0) >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR;

export const formatPctTick = (value: unknown) => `${Number(value).toFixed(1)}%`;
