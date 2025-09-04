import { useEffect, useState } from "react";
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
export function useFetchWithRetry<T>(
  fn: () => Promise<T>,
  baseDelay = 500,
  maxAttempts = 5,
): UseFetchResult<T> & {
  attempt: number;
  maxAttempts: number;
  unauthorized: boolean;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    retry(
      () => fn(),
      maxAttempts,
      baseDelay,
      (a) => {
        if (!cancelled) setAttempt(a);
      },
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
    };
  }, [fn, baseDelay, maxAttempts]);

  const unauthorized = error?.message.includes("HTTP 401") ?? false;
  return { data, loading, error, attempt, maxAttempts, unauthorized };
}

export default useFetchWithRetry;
