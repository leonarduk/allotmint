import type { Transaction } from "../types";

/** Maximum number of trade markers drawn before collapsing to first/last per side. */
export const MAX_TRADE_MARKERS = 12;

export const BUY_MARKER_COLOR = "#22c55e";
export const SELL_MARKER_COLOR = "#ef4444";

export type TradeSide = "buy" | "sell";

export type TradeMarker = {
  /** Stable key for React, derived from the transaction. */
  key: string;
  /** Date of a point that exists in the chart data, so the line lands on the axis. */
  date: string;
  /** The trade's own date, which may differ from `date` when snapped. */
  tradeDate: string;
  side: TradeSide;
  owner: string;
  account: string;
  units: number | null;
  price: number | null;
};

/**
 * Classify a transaction as a buy or a sell.
 *
 * Backends emit both upper and lower case for these values, and some rows carry
 * the value on `kind` rather than `type`, so both fields are checked case
 * insensitively.  Anything that is not clearly a purchase or a sale (dividends,
 * fees, transfers) returns null and is not marked on the chart.
 */
export function tradeSide(tx: Pick<Transaction, "type" | "kind">): TradeSide | null {
  for (const raw of [tx.type, tx.kind]) {
    if (typeof raw !== "string") continue;
    const value = raw.trim().toLowerCase();
    if (value === "buy" || value === "purchase") return "buy";
    if (value === "sell" || value === "sale") return "sell";
  }
  return null;
}

/**
 * Strip an exchange suffix so `AAPL.N` and `AAPL` compare equal.  Transaction
 * rows are not guaranteed to carry the same suffix as the instrument being
 * charted.
 */
function normaliseTicker(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  return value.trim().toUpperCase().split(".")[0];
}

export function matchesTicker(
  txTicker: string | null | undefined,
  chartTicker: string,
): boolean {
  const left = normaliseTicker(txTicker);
  return left !== "" && left === normaliseTicker(chartTicker);
}

/**
 * Snap a trade date onto the nearest date present in the chart series.
 *
 * A trade can fall on a weekend, a holiday, or any other day with no close
 * price, in which case a reference line drawn at its own date would not line up
 * with the category axis and recharts would not render it.  Trades outside the
 * span of the chart data return null so they are dropped rather than clamped
 * onto the first or last point, which would misrepresent when they happened.
 *
 * `chartDates` must be sorted ascending, which it is: the series is built from
 * price history in date order.
 */
export function snapToChartDate(
  tradeDate: string,
  chartDates: string[],
): string | null {
  if (chartDates.length === 0) return null;
  const first = chartDates[0];
  const last = chartDates[chartDates.length - 1];
  if (tradeDate < first || tradeDate > last) return null;

  // Binary search for the first date >= tradeDate, then compare it with its
  // predecessor to find the closer of the two.
  let lo = 0;
  let hi = chartDates.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (chartDates[mid] < tradeDate) lo = mid + 1;
    else hi = mid;
  }

  const atOrAfter = chartDates[lo];
  if (atOrAfter === tradeDate || lo === 0) return atOrAfter;

  const before = chartDates[lo - 1];
  const distanceAfter = Math.abs(Date.parse(atOrAfter) - Date.parse(tradeDate));
  const distanceBefore = Math.abs(Date.parse(tradeDate) - Date.parse(before));
  return distanceAfter < distanceBefore ? atOrAfter : before;
}

/**
 * Reduce a crowded set of markers to the first and last of each side.
 *
 * A heavily traded instrument can accumulate enough trades to paint the chart
 * solid, hiding the price line the markers are meant to be read against.  Past
 * the cap we keep the earliest and latest buy and the earliest and latest sell,
 * so the span of activity on each side stays visible.
 */
export function capMarkers(
  markers: TradeMarker[],
  max: number = MAX_TRADE_MARKERS,
): TradeMarker[] {
  if (markers.length <= max) return markers;

  const kept = new Set<TradeMarker>();
  for (const side of ["buy", "sell"] as const) {
    const forSide = markers.filter((m) => m.side === side);
    if (forSide.length === 0) continue;
    kept.add(forSide[0]);
    kept.add(forSide[forSide.length - 1]);
  }

  return markers.filter((m) => kept.has(m));
}

/**
 * Build the reference lines for an instrument's trade history.
 *
 * Transactions for every owner and account holding the instrument are merged
 * onto the one chart; colour encodes buy vs sell only, and the owner/account is
 * carried on each marker for the tooltip.
 */
export function buildTradeMarkers(
  transactions: Transaction[],
  chartTicker: string,
  chartDates: string[],
  max: number = MAX_TRADE_MARKERS,
): TradeMarker[] {
  const markers: TradeMarker[] = [];

  transactions.forEach((tx, index) => {
    if (!tx.date) return;
    if (!matchesTicker(tx.ticker, chartTicker)) return;

    const side = tradeSide(tx);
    if (!side) return;

    const date = snapToChartDate(tx.date, chartDates);
    if (!date) return;

    markers.push({
      key: tx.id ?? tx.external_id ?? `${tx.owner}-${tx.account}-${tx.date}-${index}`,
      date,
      tradeDate: tx.date,
      side,
      owner: tx.owner,
      account: tx.account,
      units: tx.shares ?? tx.units ?? null,
      price: tx.price_gbp ?? null,
    });
  });

  markers.sort((a, b) => a.tradeDate.localeCompare(b.tradeDate));

  return capMarkers(markers, max);
}
