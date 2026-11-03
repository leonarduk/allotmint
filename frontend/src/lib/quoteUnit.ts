// Unit labels for live quotes, shared by the classic Watchlist page and
// Plot mode's seed shed (#7203) so the two never label the same quote
// differently.

// CBOE Treasury-yield indices: their "price" is a yield in percent, not a
// currency amount or a raw index-points level.
const YIELD_INDEX_SYMBOLS = new Set(['^TNX', '^TYX', '^FVX', '^IRX']);

// Fallback used only when the quote payload doesn't carry a currency
// (see symbolUnit below). Deliberately a small, explicit table rather than
// an exhaustive exchange-suffix list, and deliberately *not* a confident
// guess for anything it doesn't recognise: mislabelling a real currency is
// worse than admitting we don't know, since the whole point of this column
// is telling a beginner what's real (#7218). In particular this table does
// NOT assume every ".L"/".DE"/".SW" listing uses that market's home
// currency -- LSE, Xetra and SIX all list plenty of USD- and
// EUR-denominated lines too, which is exactly why the live `currency` field
// (added to backend/routes/quotes.py) is preferred whenever it's present.
function symbolUnitFallback(symbol: string): string {
  if (symbol.endsWith('=X')) {
    // FX rate, e.g. EURGBP=X -> "EUR/GBP": a ratio, not a currency amount.
    const pair = symbol.slice(0, -2);
    return pair.length === 6 ? `${pair.slice(0, 3)}/${pair.slice(3)}` : 'rate';
  }
  if (YIELD_INDEX_SYMBOLS.has(symbol)) return '%';
  if (symbol.startsWith('^')) return 'pts'; // index points
  if (symbol.includes('-USD')) return 'USD'; // crypto pairs, e.g. BTC-USD
  if (symbol.endsWith('=F')) return 'USD'; // commodity futures, e.g. GC=F
  // Below this point we're guessing at an exchange's *typical* currency,
  // not reading it off the symbol the way the cases above do -- kept only
  // as a best-effort label for the common default-watchlist exchanges.
  if (symbol.endsWith('.L')) return 'GBp'; // most LSE main-market listings
  if (
    symbol.endsWith('.AS') ||
    symbol.endsWith('.PA') ||
    symbol.endsWith('.MI')
  )
    return 'EUR';
  return '—'; // unknown -- do not guess (#7218)
}

// Prefer the currency the quote payload actually reports; only fall back to
// guessing from the symbol shape when the feed didn't send one (#7218).
// `quoteType` (from the provider, see backend/routes/quotes.py) takes
// priority over a reported currency for indices: an index level is a points
// figure, not a currency amount, even when the feed also sends a currency
// code alongside it (#7232).
export function symbolUnit(
  symbol: string,
  currency: string | null | undefined,
  quoteType?: string | null
): string {
  if (quoteType === 'INDEX') return 'pts';
  if (currency) return currency;
  return symbolUnitFallback(symbol);
}
