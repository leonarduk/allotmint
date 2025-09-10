import { useEffect, useState } from "react";
import { getInstrumentDetail } from "../api";
import type { InstrumentDetail } from "../types";

// Cache full instrument detail (including metadata like name, sector and
// currency) per ticker to reuse for history and positions
const cache = new Map<string, InstrumentDetail>();

export function getCachedInstrumentHistory(ticker: string) {
  return cache.get(ticker) ?? null;
}

export async function preloadInstrumentHistory(
  tickers: string[],
  _days: number,
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
          if (cache.has(ticker)) continue;
          try {
            const res = await getInstrumentDetail(ticker, 365);
            cache.set(ticker, res);
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
 * cache responses per ticker to avoid duplicate fetches. The `days` parameter
 * is kept for API compatibility but only affects which slice of the cached
 * history consumers might read; the underlying fetch always requests 365 days
 * to cover all use cases.
 */
export function useInstrumentHistory(ticker: string, _days: number) {
  const [data, setData] = useState<InstrumentDetail | null>(
    () => cache.get(ticker) ?? null,
  );
  const [loading, setLoading] = useState(!cache.has(ticker));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let active = true;
    const cached = cache.get(ticker);
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
          const res = await getInstrumentDetail(ticker, 365);
          if (!active) return;
          cache.set(ticker, res);
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
  }, [ticker]);

  return { data, loading, error };
}

// Test helper
export function __clearInstrumentHistoryCache() {
  cache.clear();
}
