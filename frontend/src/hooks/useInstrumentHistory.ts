import { useEffect, useState } from "react";
import type { InstrumentDetail } from "../types";

// Cache full instrument detail (including metadata like name, sector and
// currency) per ticker and history range to reuse for history and positions.
const cache = new Map<string, Map<number, InstrumentDetail>>();

function getTickerCache(ticker: string) {
  let byTicker = cache.get(ticker);
  if (!byTicker) {
    byTicker = new Map<number, InstrumentDetail>();
    cache.set(ticker, byTicker);
  }
  return byTicker;
}

export function getCachedInstrumentHistory(ticker: string, days?: number) {
  const byTicker = cache.get(ticker);
  if (!byTicker) return null;
  if (typeof days === "number") {
    return byTicker.get(days) ?? null;
  }
  const first = byTicker.values().next();
  return first.done ? null : first.value;
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

export async function preloadInstrumentHistory(
  tickers: string[],
  days: number,
  concurrency = 5,
) {
  const unique = Array.from(new Set(tickers));
  const queue = unique.slice();
  const workers = Array.from(
    { length: Math.min(concurrency, queue.length) },
    () =>
      (async () => {
        while (queue.length) {
          const ticker = queue.shift();
          if (!ticker) break;
          const byTicker = cache.get(ticker);
          if (byTicker?.has(days)) continue;
          try {
            const api = await import("../api");
            const res = await api.fetchInstrumentDetailWithRetry(ticker, days);
            getTickerCache(ticker).set(days, res);
          } catch {
            // ignore errors during preloading
          }
        }
      })(),
  );
  await Promise.all(workers);
}

/**
 * Retrieve instrument detail (including mini price history and positions) and
 * cache responses per ticker to avoid duplicate fetches.
 */
export function useInstrumentHistory(ticker: string, days: number) {
  // console.debug('useInstrumentHistory invoked with', ticker, days);
  const [data, setData] = useState<InstrumentDetail | null>(
    () => cache.get(ticker)?.get(days) ?? null,
  );
  const [loading, setLoading] = useState(!cache.get(ticker)?.has(days));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let active = true;
    const cached = cache.get(ticker)?.get(days) ?? null;
    if (cached) {
      setData(cached);
      setLoading(false);
      return;
    }

    async function fetchWithRetry() {
      setLoading(true);
      setError(null);
      const maxAttempts = 3;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          const api = await import("../api");
          const res = await api.fetchInstrumentDetailWithRetry(ticker, days);
          if (!active) return;
          getTickerCache(ticker).set(days, res);
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
  }, [ticker, days]);

  return { data, loading, error };
}

// Test helper
export function __clearInstrumentHistoryCache() {
  cache.clear();
}
