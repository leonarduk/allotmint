/**
 * Utilities for encoding and decoding URL path segments.
 *
 * Owner values stored in state are always decoded (human-readable).
 * Owner values embedded in URL paths are always percent-encoded via
 * encodePathSegment before being passed to navigate().
 *
 * Note: window.location.pathname in browsers returns percent-encoded strings
 * for most characters. The segments extracted from it should be decoded with
 * decodePathSegment before being stored in state.
 */

/**
 * Decode a percent-encoded URL path segment.
 * Falls back to the raw value if the segment is malformed.
 */
export function decodePathSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch (error) {
    console.warn("Failed to decode owner path segment; using raw value", {
      segment,
      error,
    });
    return segment;
  }
}

/**
 * Encode a string for safe inclusion as a URL path segment.
 * Trims whitespace before encoding.
 */
export function encodePathSegment(segment: string): string {
  return encodeURIComponent(segment.trim());
}

/**
 * Strip the given OAuth callback params (default: code, state) from the
 * current URL's query string, preserving any other query params, and
 * replace the history entry so the params don't linger on reload/back.
 */
export function stripAuthCallbackParams(
  keys: string[] = ['code', 'state']
): void {
  const params = new URLSearchParams(window.location.search);
  keys.forEach((key) => params.delete(key));
  const search = params.toString() ? `?${params.toString()}` : '';
  window.history.replaceState(
    {},
    document.title,
    `${window.location.pathname}${search}`
  );
}

const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

/** Return the upper-cased ISIN if it is well formed, otherwise null. */
function normaliseIsin(isin: string | null | undefined): string | null {
  const value = isin?.trim().toUpperCase() ?? '';
  return ISIN_PATTERN.test(value) ? value : null;
}

/**
 * Build an investing.com link for an instrument.
 *
 * investing.com pages are keyed by name slugs (e.g. /equities/vodafone),
 * which can't be derived from a ticker, so this links to its site search.
 * The ISIN is preferred as the query because it identifies the security
 * unambiguously; stored instrument names carry share-class noise (e.g.
 * "Vodafone Group plc USD0.20 20/21") that returns no results. The base
 * ticker is the fallback: only the final ".EXCHANGE" segment is stripped,
 * so a dotted share class survives (BRK.B.N -> BRK.B).
 */
export function buildInvestingComUrl(
  isin: string | null | undefined,
  ticker: string
): string | null {
  const trimmed = ticker.trim().toUpperCase();
  const lastDot = trimmed.lastIndexOf('.');
  const baseTicker = lastDot > 0 ? trimmed.slice(0, lastDot) : trimmed;
  const query = normaliseIsin(isin) ?? baseTicker;
  if (!query) return null;
  return `https://www.investing.com/search/?q=${encodeURIComponent(query)}`;
}

const SEC_ID_PATTERN = /^[0-9A-Z]{10}$/;

/** Morningstar's quote-page section for an AllotMint instrument type. */
function morningstarSection(instrumentType: string | null | undefined): string {
  const type = (instrumentType ?? '').trim().toUpperCase();
  if (type === 'ETF' || type === 'ETC' || type === 'ETN') return 'etfs';
  if (type === 'FUND' || type === 'MUTUALFUND') return 'funds';
  if (type === 'INVESTMENT TRUST') return 'trusts';
  return 'stocks';
}

/**
 * Build a Morningstar link for an instrument.
 *
 * Morningstar quote pages are keyed by its own SecId (e.g. 0P0000AATZ),
 * one per listing, under a section for the kind of security. With a known
 * SecId this links straight to the quote page; otherwise it falls back to
 * a search by ISIN, which lists the matching listings. Returns null with
 * neither.
 */
export function buildMorningstarUrl(
  isin: string | null | undefined,
  secId?: string | null,
  instrumentType?: string | null
): string | null {
  const id = secId?.trim().toUpperCase();
  if (id && SEC_ID_PATTERN.test(id)) {
    return `https://global.morningstar.com/en-gb/investments/${morningstarSection(instrumentType)}/${id}/quote`;
  }
  const value = normaliseIsin(isin);
  if (!value) return null;
  return `https://global.morningstar.com/en-gb/search?query=${encodeURIComponent(value)}`;
}

/**
 * Build a justETF profile link for an ETF from its ISIN.
 *
 * justETF profile pages are keyed directly by ISIN, so this links straight
 * to the fund profile. Returns null without a valid ISIN; callers decide
 * whether the instrument is an ETF.
 */
export function buildJustEtfUrl(
  isin: string | null | undefined
): string | null {
  const value = normaliseIsin(isin);
  if (!value) return null;
  return `https://www.justetf.com/en/etf-profile.html?isin=${encodeURIComponent(value)}`;
}
