import { useEffect, useState } from "react";
import {
  fetchInstrumentDetailWithRetry,
  fetchInstrumentBatchWithRetry,
  type InstrumentBatchEntry,
} from "../api";
import type { InstrumentDetail, InstrumentDetailMini } from "../types";

// Cache full instrument detail (including metadata like name, sector and
// currency) per ticker and history range to reuse for history and positions.
const cache = new Map<string, Map<number, InstrumentDetail>>();

// In-flight requests keyed by `${ticker}:${days}` so concurrent callers
// (preloads, sparkline hooks, and StrictMode's double effect run) share a
// single fetch instead of firing one request per consumer.
const inFlight = new Map<string, Promise<InstrumentDetail>>();

// --- Batch (mini-only) support --------------------------------------------
//
// Sparkline/InstrumentTile only ever read `prices`/`mini`, never `positions`
// or metadata, so their data can come from the cheaper /instrument/batch
// endpoint. That endpoint's response never carries positions/name/sector/etc,
// so a batch-derived entry is kept in a *separate* cache from `cache` above:
// merging the two would let a batch response silently satisfy a later
// full-detail read with a payload that's missing fields that read needs --
// e.g. InstrumentResearch's range picker offers the same 7/30-day values a
// holdings table's sparklines preload, so the collision is routine, not a
// corner case.
type MiniDetail = Pick<InstrumentDetail, "prices" | "mini">;
const miniCache = new Map<string, Map<number, MiniDetail>>();

// Requests for the same `days` value queued within the same microtask are
// merged into one batch call, regardless of whether they came from
// preloadInstrumentHistory or an individual Sparkline/InstrumentTile mount:
// React runs a child's effects before its parent's within one commit, so
// without this a holdings table's own preload call would always lose that
// race to its (also newly mounted) row sparklines and every ticker would
// still fire its own request.
const miniPending = new Map<number, Set<string>>();
const miniFlushScheduled = new Set<number>();
const miniInFlight = new Map<string, Promise<MiniDetail | null>>();
const miniResolvers = new Map<string, (value: MiniDetail | null) => void>();

// Mirrors backend/routes/instrument.py's MAX_BATCH_TICKERS -- the batch
// endpoint 400s rather than silently truncating past this, so a flush with
// more pending tickers than fit in one request is split into several.
const MAX_BATCH_TICKERS = 100;

// --- Client-side mini derivation (ADR #6911 §5.2/§8 Phase 3b) --------------
//
// `/instrument/` no longer attaches `mini` by default (mirroring the batch
// endpoint's `include_mini` opt-in), so a full-detail cache entry populated by
// a full-detail consumer (e.g. InstrumentResearch.tsx) may have no `.mini` for
// a mini-only consumer (Sparkline/InstrumentTile) to read at the same
// (ticker, days) key. Deriving the slices client-side from `.prices` avoids
// that entry silently rendering an empty sparkline.
//
// This intentionally replicates the backend's row-count slicing --
// `out[-7:]`/`out[-30:]`/`out[-180:]` in backend/common/instrument_api.py's
// `timeseries_for_ticker` -- rather than the calendar-day cutoff described in
// ADR §4.5. That date-cutoff derivation is for slicing arbitrary ranges out of
// one canonical (e.g. 365-day) series; here `.prices` already covers exactly
// the window the entry was fetched with (resolve_date_range), so row-slicing
// the tail reproduces the same values the server's `mini` field would have
// held for that entry -- see the ADR's "why this is easy to miss" note in
// §4.5.
//
// All three windows are derived, matching the server's `mini` shape exactly
// (`{"7": ..., "30": ..., "180": ...}` regardless of the `days` the entry was
// fetched with -- the backend computes all three from whatever `prices` it
// has, not just the requested one). The current consumers (Sparkline,
// InstrumentTile) only ever read the one window matching their own fetch
// `days`, but deriving only that one would leave the other two silently
// `undefined` on this entry for any future/other reader -- a real gap between
// "derived mini" and "server mini" shape that's cheap to close outright.
const MINI_WINDOWS = [7, 30, 180] as const;

function deriveMiniRows(prices: unknown, window: number): InstrumentDetailMini[string] {
  if (!Array.isArray(prices) || window <= 0) return [];
  return prices.slice(-window);
}

function withDerivedMini<T extends { prices: unknown; mini?: InstrumentDetail["mini"] }>(
  entry: T,
): T {
  if (MINI_WINDOWS.every((window) => entry.mini?.[String(window)])) return entry;
  const mini: InstrumentDetailMini = { ...(entry.mini ?? {}) };
  for (const window of MINI_WINDOWS) {
    const key = String(window);
    if (!mini[key]) mini[key] = deriveMiniRows(entry.prices, window);
  }
  return { ...entry, mini } as T;
}

function getTickerCache(ticker: string) {
  let byTicker = cache.get(ticker);
  if (!byTicker) {
    byTicker = new Map<number, InstrumentDetail>();
    cache.set(ticker, byTicker);
  }
  return byTicker;
}

function getMiniTickerCache(ticker: string) {
  let byTicker = miniCache.get(ticker);
  if (!byTicker) {
    byTicker = new Map<number, MiniDetail>();
    miniCache.set(ticker, byTicker);
  }
  return byTicker;
}

function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

function scheduleMiniFlush(days: number) {
  if (miniFlushScheduled.has(days)) return;
  miniFlushScheduled.add(days);
  queueMicrotask(() => {
    miniFlushScheduled.delete(days);
    void flushMiniBatch(days);
  });
}

async function flushMiniBatch(days: number) {
  const tickers = Array.from(miniPending.get(days) ?? []);
  miniPending.delete(days);
  if (!tickers.length) return;

  await Promise.all(
    chunk(tickers, MAX_BATCH_TICKERS).map(async (group) => {
      let response: { instruments: Record<string, InstrumentBatchEntry>; empty: string[] } | null;
      try {
        const raw = await fetchInstrumentBatchWithRetry(group, days, true);
        // Treat an unexpectedly-shaped body the same as a failed request
        // rather than throwing on the property accesses below.
        response =
          raw && typeof raw === "object" && raw.instruments && Array.isArray(raw.empty)
            ? raw
            : null;
      } catch {
        response = null;
      }

      // The backend's dedupe_tickers collapses case-insensitive duplicates in
      // the *request* to a single spelling, so e.g. requesting both "ABC.L"
      // and "abc.l" (two accounts holding the same instrument, spelled
      // differently) gets back only one of those spellings as a response
      // key. Match case-insensitively here so every requested spelling still
      // resolves, instead of only whichever one the backend happened to keep.
      let instrumentsByUpper: Map<string, InstrumentBatchEntry> | null = null;
      let emptyUpper: Set<string> | null = null;
      if (response) {
        instrumentsByUpper = new Map(
          Object.entries(response.instruments).map(([t, entry]) => [t.toUpperCase(), entry]),
        );
        emptyUpper = new Set(response.empty.map((t) => t.toUpperCase()));
      }

      for (const ticker of group) {
        const key = `${ticker}:${days}`;
        let result: MiniDetail | null = null;

        if (instrumentsByUpper && emptyUpper) {
          const entry = instrumentsByUpper.get(ticker.toUpperCase());
          if (entry) {
            result = { prices: entry.prices, mini: entry.mini };
            getMiniTickerCache(ticker).set(days, result);
          } else if (emptyUpper.has(ticker.toUpperCase())) {
            result = { prices: [] };
            getMiniTickerCache(ticker).set(days, result);
          }
          // Anything else (the `unknown` bucket, or a batch-level failure) is
          // left uncached, matching the "failures are not cached" contract
          // below so a later call retries instead of pinning a miss forever.
        }

        miniResolvers.get(key)?.(result);
        miniResolvers.delete(key);
        miniInFlight.delete(key);
      }
    }),
  );
}

/** Request mini/prices for one ticker, coalesced with any other request for the same `days` queued in this microtask. */
function requestMiniHistory(ticker: string, days: number): Promise<MiniDetail | null> {
  const key = `${ticker}:${days}`;
  const existing = miniInFlight.get(key);
  if (existing) return existing;

  const promise = new Promise<MiniDetail | null>((resolve) => {
    miniResolvers.set(key, resolve);
  });
  miniInFlight.set(key, promise);

  let pending = miniPending.get(days);
  if (!pending) {
    pending = new Set();
    miniPending.set(days, pending);
  }
  pending.add(ticker);
  scheduleMiniFlush(days);

  return promise;
}

export function getCachedInstrumentHistory(
  ticker: string,
  days?: number,
): InstrumentDetail | MiniDetail | null {
  const byTicker = cache.get(ticker);
  if (typeof days === "number") {
    const full = byTicker?.get(days);
    if (full) return withDerivedMini(full);
    return miniCache.get(ticker)?.get(days) ?? null;
  }
  const first = byTicker?.values().next();
  if (first && !first.done) return first.value;
  const miniFirst = miniCache.get(ticker)?.values().next();
  return miniFirst && !miniFirst.done ? miniFirst.value : null;
}

export function updateCachedInstrumentHistory(
  ticker: string,
  updater: (detail: InstrumentDetail) => void,
  days?: number,
) {
  const byTicker = cache.get(ticker);
  if (!byTicker) return;
  if (typeof days === "number") {
    const entry = byTicker.get(days);
    if (entry) updater(entry);
    return;
  }
  for (const entry of byTicker.values()) {
    updater(entry);
  }
}

function hasNoHistory(detail: { prices: unknown }): boolean {
  return Array.isArray(detail.prices) && detail.prices.length === 0;
}

/**
 * Fetch full instrument detail for (ticker, days) exactly once while a request is
 * in flight: completed results come from the cache, concurrent callers await
 * the same in-flight promise, and only a genuinely new (ticker, days) starts a
 * network request. Failures are not cached so a later effect run can retry.
 */
async function fetchInstrumentDetailShared(
  ticker: string,
  days: number,
): Promise<InstrumentDetail> {
  const cached = cache.get(ticker)?.get(days);
  if (cached) return cached;

  const key = `${ticker}:${days}`;
  const pending = inFlight.get(key);
  if (pending) return pending;

  const promise = (async () => {
    try {
      const res = await fetchInstrumentDetailWithRetry(ticker, days);
      getTickerCache(ticker).set(days, res);
      return res;
    } finally {
      inFlight.delete(key);
    }
  })();

  inFlight.set(key, promise);
  return promise;
}

/**
 * Preload instrument history for a batch of tickers and return the subset that
 * resolved to a known ticker with an empty history. Consumers use this to
 * surface one consolidated "no price history" notice instead of per-ticker
 * errors. Successful responses (including empty ones) are cached, so later
 * calls do not re-fetch.
 *
 * Fetches through the shared mini/batch path (see requestMiniHistory): a
 * ticker already covered by a full single-ticket fetch (elsewhere in the app)
 * is reused as-is, everything else collapses into one /instrument/batch call
 * per distinct `days` value instead of one request per ticker.
 */
export async function preloadInstrumentHistory(
  tickers: string[],
  days: number,
): Promise<string[]> {
  const unique = Array.from(new Set(tickers));
  const results = await Promise.all(
    unique.map(async (ticker) => {
      const full = cache.get(ticker)?.get(days);
      if (full) return hasNoHistory(full) ? ticker : null;

      const cachedMini = miniCache.get(ticker)?.get(days);
      const mini = cachedMini ?? (await requestMiniHistory(ticker, days));
      if (!mini) return null; // unknown ticker, or the batch request failed -- ignored, as a failed preload always has been
      return hasNoHistory(mini) ? ticker : null;
    }),
  );
  return results.filter((ticker): ticker is string => ticker !== null);
}

/**
 * Retrieve instrument detail and cache responses per ticker to avoid
 * duplicate fetches.
 *
 * By default this fetches the full detail (positions, name, sector, etc.) via
 * the single-ticket endpoint. Pass `acceptMiniOnly: true` for a
 * sparkline-style consumer that only reads `prices`/`mini`: it accepts a
 * cache hit from the cheaper batch path (see preloadInstrumentHistory) and
 * falls back to requesting just that path when nothing is cached yet.
 */
export function useInstrumentHistory(
  ticker: string,
  days: number,
): { data: InstrumentDetail | null; loading: boolean; error: Error | null };
export function useInstrumentHistory(
  ticker: string,
  days: number,
  options: { acceptMiniOnly: true },
): { data: MiniDetail | null; loading: boolean; error: Error | null };
export function useInstrumentHistory(
  ticker: string,
  days: number,
  options?: { acceptMiniOnly?: boolean },
) {
  const acceptMiniOnly = options?.acceptMiniOnly ?? false;

  const [data, setData] = useState<InstrumentDetail | MiniDetail | null>(() => {
    const cachedFull = cache.get(ticker)?.get(days);
    if (cachedFull) return acceptMiniOnly ? withDerivedMini(cachedFull) : cachedFull;
    return acceptMiniOnly ? (miniCache.get(ticker)?.get(days) ?? null) : null;
  });
  const [loading, setLoading] = useState(() => {
    if (cache.get(ticker)?.has(days)) return false;
    if (acceptMiniOnly && miniCache.get(ticker)?.has(days)) return false;
    return true;
  });
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!ticker || days <= 0) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    let active = true;

    const cachedFull = cache.get(ticker)?.get(days) ?? null;
    if (cachedFull) {
      setData(acceptMiniOnly ? withDerivedMini(cachedFull) : cachedFull);
      setLoading(false);
      return;
    }

    if (acceptMiniOnly) {
      const cachedMini = miniCache.get(ticker)?.get(days) ?? null;
      if (cachedMini) {
        setData(cachedMini);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      requestMiniHistory(ticker, days).then((mini) => {
        if (!active) return;
        setData(mini);
        setLoading(false);
      });
      return () => {
        active = false;
      };
    }

    async function fetchWithRetry() {
      setLoading(true);
      setError(null);
      const maxAttempts = 3;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          const res = await fetchInstrumentDetailShared(ticker, days);
          if (!active) return;
          setData(res);
          return;
        } catch (e) {
          const err = e instanceof Error ? e : new Error(String(e));
          if (err.message.includes("HTTP 429")) {
            // Prefer server-provided Retry-After header over exponential backoff
            let delay: number | undefined;
            const retryAfter =
              // Some fetch wrappers attach the response for easier introspection
              (err as any).response?.headers?.get?.("Retry-After") ??
              (err as any).headers?.get?.("Retry-After");

            if (retryAfter) {
              // Retry-After can be seconds or an HTTP-date
              const seconds = Number(retryAfter);
              if (!Number.isNaN(seconds)) {
                delay = seconds * 1000;
              } else {
                const dateMs = Date.parse(retryAfter);
                if (!Number.isNaN(dateMs)) delay = dateMs - Date.now();
              }
            }

            if (delay == null || delay <= 0) {
              delay = 500 * 2 ** attempt;
            }
            // Add a small random jitter to avoid synchronized retries
            delay += Math.random() * 100;
            await new Promise((r) => setTimeout(r, delay));
            continue;
          }
          if (active) setError(err);
          return;
        }
      }
      // All retries failed with 429
      if (active) setError(new Error("HTTP 429 – Too Many Requests"));
    }

    fetchWithRetry().finally(() => {
      if (active) setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [ticker, days, acceptMiniOnly]);

  return { data, loading, error };
}

// Test helper
export function __clearInstrumentHistoryCache() {
  cache.clear();
  inFlight.clear();
  miniCache.clear();
  miniPending.clear();
  miniFlushScheduled.clear();
  miniInFlight.clear();
  miniResolvers.clear();
}
