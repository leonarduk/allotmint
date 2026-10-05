// Shared price-precision logic for components that display prices.
//
// Decimal precision for a price-like value. This used to be duplicated
// between formatValue and formatChange in Watchlist.tsx with two different
// rule sets -- formatChange was hardcoded to toFixed(2), so an EURGBP=X move
// that formatValue correctly rendered to 5 decimal places (0.85721) showed
// up as "+0.00" in the Chg column even though Chg % reported it correctly.
// Both formatters now call this single function so the rules can't drift
// apart again (#7218).
//
// `val` is the value actually being formatted (Last/Open/High/Low, or the
// day's Change) and drives the ">10000" 0dp rule, exactly as before.
// `refPrice` is the instrument's own price level and is used *only* for the
// sub-$1-crypto check: a day's Change can be small, negative or zero
// regardless of whether the instrument itself trades under $1, so that one
// decision can't be made from `val` alone the way ">10000" can. It defaults
// to `val` so formatValue's behaviour (call site passes no third argument)
// is completely unchanged.
export function priceDecimals(
  symbol: string,
  val: number,
  refPrice: number = val,
): number {
  if (symbol.endsWith("=X")) return 5;
  if (symbol === "^TNX") return 3;
  // Math.abs(refPrice), not "val < 1": a *sign* on the value being
  // formatted shouldn't change decimal precision, and using the change's
  // own (possibly negative, possibly large) value here was a regression
  // caught in review -- every negative crypto change is "< 1" under the
  // literal comparison, so BTC-USD's "-124" change rendered as "-124.00000"
  // (5dp) while a "+124" change rendered "+124.00" (2dp), same symbol and
  // column. Keying off the instrument's Last price instead fixes that while
  // leaving the ">10000" rule keyed off `val` itself, since that rule is
  // about the value being displayed, not the instrument's price level
  // (#7218).
  if (symbol.includes("-USD") && Math.abs(refPrice) < 1) return 5;
  if (val > 10000) return 0;
  return 2;
}
