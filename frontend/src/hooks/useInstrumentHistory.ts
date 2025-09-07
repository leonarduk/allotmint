import { useEffect, useState } from "react";
import { getInstrumentDetail } from "../api";
import type { InstrumentDetailMini } from "../types";

// Simple in-memory cache keyed by ticker+days
const cache = new Map<string, InstrumentDetailMini>();

export function getCachedInstrumentHistory(
  ticker: string,
  days: number,
) {
  return cache.get(`${ticker}:${days}`) ?? null;
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
          const key = `${ticker}:${days}`;
          if (cache.has(key)) continue;
          try {
            const res = await getInstrumentDetail(ticker, days);
            if (res.mini) {
              cache.set(key, res.mini);
            }
          } catch {
            // ignore errors during preloading
          }
        }
      })(),
  );
  await Promise.all(workers);
}

/**
 * Retrieve mini history for an instrument and cache responses to avoid
 * refetching on re-renders. Subsequent calls with the same ticker and days
 * return the cached result immediately.
 */
export function useInstrumentHistory(ticker: string, days: number) {
  const key = `${ticker}:${days}`;
  const [data, setData] = useState<InstrumentDetailMini | null>(
    () => cache.get(key) ?? null,
  );
  const [loading, setLoading] = useState(!cache.has(key));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let active = true;
    const cached = cache.get(key);
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
          const res = await getInstrumentDetail(ticker, days);
          if (!active) return;
          if (res.mini) {
            cache.set(key, res.mini);
            setData(res.mini);
          }
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
      if (active)
        setError(new Error("HTTP 429 – Too Many Requests"));
    }

    fetchWithRetry().finally(() => {
      if (active) setLoading(false);
    });

    return () => {
      active = false;
    };
  }, [ticker, days, key]);

  return { data, loading, error };
}
