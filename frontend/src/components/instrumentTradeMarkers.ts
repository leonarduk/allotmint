import { transactionUnits } from "../lib/transactionQuantity";
import type { Transaction } from "../types";

/** Maximum number of trade markers drawn before each side is thinned evenly. */
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
 * Exchange codes that may follow a ticker's final `.`: the app's own codes
 * plus their Yahoo suffix forms (see `_YAHOO_SUFFIXES` / `_EXCHANGE_REGIONS`
 * in `backend/common/instruments.py`).  Share-class letters such as the `A`
 * and `B` of `BRK.A`/`BRK.B` are deliberately absent, so those stay distinct.
 */
const KNOWN_EXCHANGE_SUFFIXES: ReadonlySet<string> = new Set([
  "L",
  "LSE",
  "UK",
  "N",
  "O",
  "NYSE",
  "NASDAQ",
  "US",
  "PA",
  "PARIS",
  "DE",
  "XETRA",
  "F",
  "TO",
  "TSX",
  "AX",
  "ASX",
  "MI",
]);

/**
 * Strip a known exchange suffix so `AAPL.N` and `AAPL` compare equal.
 * Transaction rows are not guaranteed to carry the same suffix as the
 * instrument being charted.  An unrecognised suffix is kept, so `BRK.A` and
 * `BRK.B` (or `FOO.XYZ` and `FOO`) never match each other (#7798).
 */
function normaliseTicker(value: string | null | undefined): string {
  if (typeof value !== "string") return "";
  const ticker = value.trim().toUpperCase();
  const dot = ticker.lastIndexOf(".");
  if (dot <= 0) return ticker;
  const suffix = ticker.slice(dot + 1);
  return KNOWN_EXCHANGE_SUFFIXES.has(suffix) ? ticker.slice(0, dot) : ticker;
}

export function matchesTicker(
  txTicker: string | null | undefined,
  chartTicker: string,
): boolean {
  const left = normaliseTicker(txTicker);
  return left !== "" && left === normaliseTicker(chartTicker);
}

/**
 * Reduce a date to its `YYYY-MM-DD` day part.
 *
 * Transaction rows are not consistent about this: some carry a plain date,
 * while those converted from the portfolio XML carry a full timestamp such as
 * `2019-08-27T00:00`.  The chart's category axis is keyed on plain dates, so
 * comparing the two forms directly is wrong — `"2026-09-17T00:00"` sorts after
 * `"2026-09-17"`, which silently dropped any trade falling on the last charted
 * day.
 */
export function dayPart(value: string): string {
  return value.slice(0, 10);
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
  rawTradeDate: string,
  chartDates: string[],
): string | null {
  if (chartDates.length === 0) return null;
  const tradeDate = dayPart(rawTradeDate);
  const first = dayPart(chartDates[0]);
  const last = dayPart(chartDates[chartDates.length - 1]);
  if (tradeDate < first || tradeDate > last) return null;

  // Binary search for the first date >= tradeDate, then compare it with its
  // predecessor to find the closer of the two.
  let lo = 0;
  let hi = chartDates.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dayPart(chartDates[mid]) < tradeDate) lo = mid + 1;
    else hi = mid;
  }

  const atOrAfter = chartDates[lo];
  if (dayPart(atOrAfter) === tradeDate || lo === 0) return atOrAfter;

  const before = chartDates[lo - 1];
  // Parsed as UTC midnight on both sides, so the comparison is not skewed by
  // the viewer's timezone.
  const distanceAfter = Math.abs(Date.parse(dayPart(atOrAfter)) - Date.parse(tradeDate));
  const distanceBefore = Math.abs(Date.parse(tradeDate) - Date.parse(dayPart(before)));
  return distanceAfter < distanceBefore ? atOrAfter : before;
}

/** Smallest share of the budget a side with trades is given (#7797). */
const MIN_MARKERS_PER_SIDE = 2;

/**
 * Pick `count` evenly spaced markers from `markers`, always keeping the first
 * and the last so the span of activity stays visible.
 */
function thinEvenly(markers: TradeMarker[], count: number): TradeMarker[] {
  if (count >= markers.length) return markers;
  if (count <= 0) return [];
  if (count === 1) return [markers[0]];
  // The step is >= 1 because count < markers.length, so the rounded indices
  // are strictly increasing and never pick the same marker twice.
  const step = (markers.length - 1) / (count - 1);
  return Array.from({ length: count }, (_, i) => markers[Math.round(i * step)]);
}

/**
 * Split the `max` budget between buys and sells in proportion to how many of
 * each there are, giving every side that has trades at least
 * MIN_MARKERS_PER_SIDE (or all of them, if it has fewer) and never more than
 * it has.
 */
function sideBudgets(buys: number, sells: number, max: number): [number, number] {
  const minBuys = Math.min(MIN_MARKERS_PER_SIDE, buys);
  const minSells = Math.min(MIN_MARKERS_PER_SIDE, sells);
  let buyBudget = Math.round((max * buys) / (buys + sells));
  buyBudget = Math.min(Math.max(buyBudget, minBuys), buys, Math.max(max - minSells, 0));
  const sellBudget = Math.min(sells, max - buyBudget);
  // Hand any budget the sells could not use back to the buys.
  buyBudget = Math.min(buys, max - sellBudget);
  return [buyBudget, sellBudget];
}

/**
 * Thin a crowded set of markers down to at most `max`.
 *
 * A heavily traded instrument can accumulate enough trades to paint the chart
 * solid, hiding the price line the markers are meant to be read against.  Past
 * the cap the budget is shared between buys and sells in proportion to their
 * counts, and each side is thinned to evenly spaced trades that keep its
 * earliest and latest -- so a one-sided history keeps a representative spread
 * rather than collapsing to its two endpoints (#7797).  Callers can surface
 * `markers.length - result.length` as the number of hidden trades.
 */
export function capMarkers(
  markers: TradeMarker[],
  max: number = MAX_TRADE_MARKERS,
): TradeMarker[] {
  if (markers.length <= max) return markers;

  const buys = markers.filter((m) => m.side === "buy");
  const sells = markers.filter((m) => m.side === "sell");
  const [buyBudget, sellBudget] = sideBudgets(buys.length, sells.length, max);

  return [...thinEvenly(buys, buyBudget), ...thinEvenly(sells, sellBudget)].sort(
    (a, b) => a.tradeDate.localeCompare(b.tradeDate),
  );
}

/**
 * Collect every chartable trade marker for an instrument, sorted by trade
 * date and not yet capped.
 *
 * Transactions for every owner and account holding the instrument are merged
 * onto the one chart; colour encodes buy vs sell only, and the owner/account is
 * carried on each marker for the tooltip.
 */
export function collectTradeMarkers(
  transactions: Transaction[],
  chartTicker: string,
  chartDates: string[],
): TradeMarker[] {
  const markers: TradeMarker[] = [];

  transactions.forEach((tx, index) => {
    if (!tx.date) return;
    // Reconciliation injects balancing entries, dated a year in the past, when
    // a holding cannot be explained by the recorded trades.  Drawing them would
    // claim the owner traded on a date they did not, which is exactly the
    // question this overlay exists to answer.
    if (tx.synthetic) return;
    // Rows converted from the portfolio XML carry only `security_ref`, an index
    // into that XML rather than a ticker, so they cannot be attributed to an
    // instrument here and are skipped rather than mis-attributed.
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
      units: transactionUnits(tx),
      price: tx.price_gbp ?? null,
    });
  });

  markers.sort((a, b) => a.tradeDate.localeCompare(b.tradeDate));

  return markers;
}

/** Build the (capped) reference lines for an instrument's trade history. */
export function buildTradeMarkers(
  transactions: Transaction[],
  chartTicker: string,
  chartDates: string[],
  max: number = MAX_TRADE_MARKERS,
): TradeMarker[] {
  return capMarkers(collectTradeMarkers(transactions, chartTicker, chartDates), max);
}
