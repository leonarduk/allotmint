/** One price series to overlay on the comparison chart. */
export type CompareSeries = {
  ticker: string;
  points: { date: string; close: number }[];
};

/** A chart row: the date plus one `s<index>` % change value per series. */
export type CompareRow = { date: string } & Record<string, number | string>;

/** Most series the comparison chart accepts, so the lines stay readable. */
export const MAX_COMPARE_SERIES = 6;

export const COMPARE_COLORS = [
  "#1a73e8",
  "#e8710a",
  "#137333",
  "#a142f4",
  "#d01884",
  "#007b83",
];

/**
 * Read the `compare` URL parameter (comma-separated tickers) into a clean
 * list: upper-cased, de-duplicated, without the page's own ticker, and capped
 * so a hand-edited link can't exceed what the chart accepts.
 */
export function parseCompareParam(
  value: string | null,
  baseTicker: string,
): string[] {
  const base = baseTicker.toUpperCase();
  const tickers = (value ?? "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter((t) => /^[A-Z0-9.-]{1,16}$/.test(t) && t !== base);
  return [...new Set(tickers)].slice(0, MAX_COMPARE_SERIES - 1);
}

/**
 * Recharts reads dots in a dataKey as a nested path, and tickers such as
 * `VWRL.L` contain dots, so series are keyed by position instead.
 */
export const compareKey = (index: number): string => `s${index}`;

/**
 * Merge several price series into rows of % change, each rebased to 0 on the
 * first date every series has data for.  Series start on different dates
 * (a recent listing, a gap in the cache), and rebasing each one on its own
 * first point would compare returns over different periods.
 */
export function buildCompareRows(series: CompareSeries[]): CompareRow[] {
  const usable = series.map((s) =>
    [...s.points]
      .filter((p) => Number.isFinite(p.close) && p.close > 0)
      .sort((a, b) => a.date.localeCompare(b.date)),
  );
  if (usable.some((points) => points.length === 0)) return [];

  const commonStart = usable.reduce(
    (latest, points) => (points[0].date > latest ? points[0].date : latest),
    "",
  );
  const rows = new Map<string, CompareRow>();
  usable.forEach((points, index) => {
    const inRange = points.filter((p) => p.date >= commonStart);
    const base = inRange[0]?.close;
    if (!base) return;
    for (const p of inRange) {
      const row = rows.get(p.date) ?? { date: p.date };
      row[compareKey(index)] = (p.close / base - 1) * 100;
      rows.set(p.date, row);
    }
  });
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}
