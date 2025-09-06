import { useEffect, useState } from "react";
import { getInstrumentDetail } from "../api";
import type { InstrumentDetailMini } from "../types";

// Simple in-memory cache keyed by ticker+days
const cache = new Map<string, InstrumentDetailMini>();

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

    setLoading(true);
    getInstrumentDetail(ticker, days)
      .then((res) => {
        if (!active) return;
        if (res.mini) {
          cache.set(key, res.mini);
          setData(res.mini);
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [ticker, days, key]);

  return { data, loading, error };
}
