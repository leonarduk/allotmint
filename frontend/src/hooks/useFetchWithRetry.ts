import { useEffect, useRef, useState, type DependencyList } from "react";
import retry from "../utils/retry";

interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

/**
 * Wraps a fetcher and retries with exponential backoff.
 * Retries stop after `maxAttempts` and the final error is surfaced to callers.
 */
/**
 * `fn` should be memoized to avoid unnecessary retries on each render.
 */
export function useFetchWithRetry<T>(
  fn: () => Promise<T>,
  baseDelay = 500,
  maxAttempts = 5,
  deps: DependencyList = [],
): UseFetchResult<T> & {
  attempt: number;
  maxAttempts: number;
  unauthorized: boolean;
} {
  if (baseDelay <= 0) {
    throw new Error("baseDelay must be positive");
  }

  const fnRef = useRef(fn);
  fnRef.current = fn;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);

    retry(
      () => fnRef.current(),
      maxAttempts,
      baseDelay,
      (a) => {
        if (!cancelled) setAttempt(a);
      },
      controller.signal,
    )
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [baseDelay, maxAttempts, ...deps]);

  const unauthorized = error?.message.includes("HTTP 401") ?? false;
  return { data, loading, error, attempt, maxAttempts, unauthorized };
}

export default useFetchWithRetry;
