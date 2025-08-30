import { useEffect, useState } from "react";
import useFetch from "./useFetch";

/**
 * Wraps `useFetch` and automatically retries the request until it succeeds.
 * A failed request schedules another attempt after `delay` milliseconds.
 * Retries stop after `maxAttempts` attempts and the final error is surfaced
 * to callers.
 */
export function useFetchWithRetry<T>(
  fn: () => Promise<T>,
  delay = 2000,
  maxAttempts = 5,
) {
  const [attempt, setAttempt] = useState(1);
  const result = useFetch(fn, [attempt]);
  const unauthorized = result.error?.message.includes("HTTP 401") ?? false;

  useEffect(() => {
    if (!result.error) return;
    if (attempt >= maxAttempts) return;
    const timer = setTimeout(() => setAttempt((a) => a + 1), delay);
    return () => clearTimeout(timer);
  }, [result.error, delay, attempt, maxAttempts]);

  return { ...result, attempt, maxAttempts };
}

export default useFetchWithRetry;
