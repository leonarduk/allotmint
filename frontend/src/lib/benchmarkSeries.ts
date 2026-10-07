import type { AlphaSeriesPoint } from "../types";

export interface CumulativeComparisonPoint {
  date: string;
  portfolio: number;
  benchmark: number;
}

/**
 * Portfolio-vs-benchmark cumulative returns for the Cumulative Return chart (#7833).
 *
 * Built only from the alpha endpoint's ``series``: the backend inner-joins the
 * portfolio and benchmark daily returns before compounding them
 * (``backend/common/portfolio_utils.py:_alpha_vs_benchmark``), so every point
 * carries both values for the same date and the two lines can never cover
 * different date ranges. Points with a non-finite value are dropped as a pair
 * for the same reason. Returns an empty array when there is nothing to plot.
 */
export function buildCumulativeComparison(
  series: AlphaSeriesPoint[] | null | undefined,
): CumulativeComparisonPoint[] {
  if (!series?.length) return [];
  return series
    .filter(
      (p) =>
        typeof p.date === "string" &&
        Number.isFinite(p.portfolio_cumulative_return) &&
        Number.isFinite(p.benchmark_cumulative_return),
    )
    .map((p) => ({
      date: p.date,
      portfolio: p.portfolio_cumulative_return,
      benchmark: p.benchmark_cumulative_return,
    }));
}
