import type { InstrumentPosition, OwnerSummary } from "@/types";
import type { TradeType } from "./transactionForm";

/** Unit the trade price is typed in: pounds, or pence (GBX). */
export type PriceUnit = "GBP" | "GBX";

/** One owner/account the trade can be booked to. */
export type TradeAccount = {
  owner: string;
  account: string;
  /** Units of this instrument currently held there (0 when none). */
  heldUnits: number;
};

const accountKey = (owner: string, account: string) =>
  `${owner.toLowerCase()}/${account.toLowerCase()}`;

/**
 * Default the price unit from the instrument's quote currency: LSE lines
 * quoted in pence (GBX / GBp) default to pence so the price can be typed
 * exactly as the broker contract note shows it.
 */
export function defaultPriceUnit(quoteCurrency: string | null | undefined): PriceUnit {
  const ccy = (quoteCurrency ?? "").trim();
  return ccy === "GBp" || ccy.toUpperCase() === "GBX" ? "GBX" : "GBP";
}

/** Convert a typed price to the `price_gbp` the API expects (NaN when invalid). */
export function toPriceGbp(priceText: string, unit: PriceUnit): number {
  const price = Number(priceText);
  if (!priceText.trim() || !Number.isFinite(price)) return Number.NaN;
  // Round away binary noise from the /100 (28889.4 / 100 is not exactly
  // 288.894 in floating point) without losing any precision a broker quotes.
  return unit === "GBX" ? Math.round(price * 1e6) / 1e8 : price;
}

/**
 * Cash value of the trade in GBP: what a BUY costs (consideration plus fees)
 * or what a SELL returns (consideration minus fees). Null until units and
 * price are both valid.
 */
export function tradeTotalGbp(
  side: TradeType,
  units: number,
  priceGbp: number,
  fees: number,
): number | null {
  if (!Number.isFinite(units) || !Number.isFinite(priceGbp) || units <= 0 || priceGbp <= 0) {
    return null;
  }
  const consideration = units * priceGbp;
  const safeFees = Number.isFinite(fees) && fees > 0 ? fees : 0;
  return side === "SELL" ? consideration - safeFees : consideration + safeFees;
}

/**
 * Every owner/account the trade can go to: accounts already holding the
 * instrument first (with their units), then the rest of each owner's
 * accounts. Owner/account matching is case-insensitive.
 */
export function buildTradeAccounts(
  positions: InstrumentPosition[],
  owners: OwnerSummary[],
): TradeAccount[] {
  const byKey = new Map<string, TradeAccount>();
  for (const pos of positions) {
    if (!pos.owner || !pos.account) continue;
    const key = accountKey(pos.owner, pos.account);
    const units = Number(pos.units ?? 0);
    const prev = byKey.get(key);
    byKey.set(key, {
      owner: pos.owner,
      account: pos.account,
      heldUnits: (prev?.heldUnits ?? 0) + (Number.isFinite(units) ? units : 0),
    });
  }
  for (const summary of owners) {
    for (const account of summary.accounts ?? []) {
      const key = accountKey(summary.owner, account);
      if (!byKey.has(key)) {
        byKey.set(key, { owner: summary.owner, account, heldUnits: 0 });
      }
    }
  }
  return Array.from(byKey.values()).sort((a, b) => b.heldUnits - a.heldUnits);
}

/** Stable value for an account option. */
export function tradeAccountValue(entry: Pick<TradeAccount, "owner" | "account">): string {
  return `${entry.owner}\u0000${entry.account}`;
}

/** True when a SELL of `units` exceeds what the account holds. */
export function isOversell(side: TradeType, units: number, account: TradeAccount | undefined): boolean {
  if (side !== "SELL" || !account || !Number.isFinite(units)) return false;
  return units > account.heldUnits + 1e-9;
}
