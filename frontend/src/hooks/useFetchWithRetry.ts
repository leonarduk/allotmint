import { useEffect, useState } from "react";
import useFetch from "./useFetch";

/**
 * Wraps `useFetch` and automatically retries the request until it succeeds.
 * A failed request schedules another attempt after `delay` milliseconds.
 */
export function useFetchWithRetry<T>(fn: () => Promise<T>, delay = 2000) {
  const [attempt, setAttempt] = useState(0);
  const result = useFetch(fn, [attempt]);
  const unauthorized = result.error?.message.includes("HTTP 401") ?? false;

  useEffect(() => {
    if (!result.error || unauthorized) return;
    const timer = setTimeout(() => setAttempt((a) => a + 1), delay);
    return () => clearTimeout(timer);
  }, [result.error, delay, unauthorized]);

  return { ...result, unauthorized };
}

export default useFetchWithRetry;
