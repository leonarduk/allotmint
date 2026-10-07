/** Helpers for the look-through views (#9974). */

const MAX_WEIGHT_ROWS = 15;

/** The largest ``MAX_WEIGHT_ROWS - 1`` rows plus one row summing the rest, labelled ``otherLabel``. */
export const foldWeightRows = (
  rows: { label: string; weight_pct: number }[],
  otherLabel: (count: number) => string
): { label: string; weight_pct: number }[] => {
  if (rows.length <= MAX_WEIGHT_ROWS) return rows;
  const head = rows.slice(0, MAX_WEIGHT_ROWS - 1);
  const tail = rows.slice(MAX_WEIGHT_ROWS - 1);
  const rest = tail.reduce((sum, r) => sum + r.weight_pct, 0);
  return [...head, { label: otherLabel(tail.length), weight_pct: rest }];
};
