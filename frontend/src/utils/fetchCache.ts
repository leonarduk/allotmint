/**
 * Module-scoped result cache shared by `useFetch` (see `hooks/useFetch.ts`).
 *
 * The problem it exists to solve: `useFetch` used to hold its result in
 * component state and nothing else, so every unmount threw the data away.
 * Navigating off the portfolio overview and back re-fired the whole page's
 * request set from cold -- including `/portfolio-group/all`, measured at
 * 10.7s in #7215 -- behind a blank skeleton, even though the answer had been
 * on screen seconds earlier.
 *
 * Entries live at module scope, so they outlive unmount but not a page
 * reload. That is deliberate: this is a "don't refetch what we just fetched"
 * cache, not a persistence layer. Nothing here touches localStorage.
 *
 * `getCachedGroupInstruments` in `api.ts` predates this and keeps its own
 * (never-expiring) map for the one endpoint it covers; it is left alone.
 */

export type FetchCacheEntry<T> = {
  value: T;
  /** `Date.now()` when the value was stored, used for staleness checks. */
  storedAt: number;
};

const entries = new Map<string, FetchCacheEntry<unknown>>();

/**
 * In-flight requests keyed the same way as `entries`, so two components
 * mounting in the same commit with the same key share one request instead of
 * racing. Cleared as soon as the promise settles -- a rejected promise is
 * never left behind, or a failed load would replay the same failure to every
 * later caller with no new request (the trap `getCachedGroupInstruments`
 * documents at api.ts:753).
 */
const inFlight = new Map<string, Promise<unknown>>();

export const readFetchCache = <T>(key: string): FetchCacheEntry<T> | undefined =>
  entries.get(key) as FetchCacheEntry<T> | undefined;

export const writeFetchCache = <T>(key: string, value: T): void => {
  entries.set(key, { value, storedAt: Date.now() });
};

/** True when `entry` is younger than `ttlMs`. A non-positive TTL is never fresh. */
export const isFresh = (entry: FetchCacheEntry<unknown>, ttlMs: number): boolean =>
  ttlMs > 0 && Date.now() - entry.storedAt < ttlMs;

/**
 * Run `fn` under `key`, sharing an already-running call for the same key.
 * The result is written to the cache; a rejection is not.
 */
export const runDeduped = <T>(key: string, fn: () => Promise<T>): Promise<T> => {
  const existing = inFlight.get(key) as Promise<T> | undefined;
  if (existing) return existing;

  const promise = fn()
    .then((value) => {
      writeFetchCache(key, value);
      return value;
    })
    .finally(() => {
      if (inFlight.get(key) === promise) inFlight.delete(key);
    });

  inFlight.set(key, promise);
  return promise;
};

/**
 * Drop cached results. With no argument, drops everything; with a `prefix`,
 * drops every key starting with it (e.g. `"portfolio-group:"`).
 *
 * Tests must call this between cases -- the cache is module state and would
 * otherwise leak a previous test's response into the next one.
 */
export const clearFetchCache = (prefix?: string): void => {
  if (prefix === undefined) {
    entries.clear();
    inFlight.clear();
    return;
  }
  for (const key of [...entries.keys()]) {
    if (key.startsWith(prefix)) entries.delete(key);
  }
  for (const key of [...inFlight.keys()]) {
    if (key.startsWith(prefix)) inFlight.delete(key);
  }
};
