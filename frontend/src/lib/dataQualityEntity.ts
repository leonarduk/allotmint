/** Labels and research-page symbols for data-quality issue entities. */

export function entityLabel(entity: Record<string, unknown>): string {
  const holding = entity.holding as string | undefined;
  const ticker = entity.ticker as string | undefined;
  const exchange = entity.exchange as string | undefined;
  const owner = entity.owner as string | undefined;
  const account = entity.account as string | undefined;
  const parts: string[] = [];
  if (owner) parts.push(String(owner));
  if (account) parts.push(String(account));
  if (holding) parts.push(holding);
  else if (ticker) parts.push(exchange ? `${ticker}.${exchange}` : ticker);
  return parts.join(" / ") || "—";
}

// InstrumentResearch (/research/:ticker) only resolves tickers of this shape.
const LINKABLE_TICKER = /^[A-Za-z0-9.-]{1,10}$/;

/** Full "TICKER.EXCHANGE" symbol for an issue entity, or null if it has no research page. */
export function researchSymbol(entity: Record<string, unknown>): string | null {
  const ticker = entity.ticker as string | undefined;
  const exchange = entity.exchange as string | undefined;
  const holding = entity.holding as string | undefined;
  const symbol = ticker ? (exchange ? `${ticker}.${exchange}` : ticker) : holding;
  return symbol && LINKABLE_TICKER.test(symbol) ? symbol : null;
}
