import { toast } from "react-toastify";

/**
 * Retry a function with exponential backoff. The delay after each failed
 * attempt grows by `base` * 2^(attempt-1).
 *
 * `fn` is invoked up to `attempts` times until it resolves. The optional
 * `onAttempt` callback is invoked before each attempt (1-indexed).
 */
export async function retry<T>(
  fn: () => Promise<T>,
  attempts = 5,
  base = 500,
  onAttempt?: (attempt: number) => void,
): Promise<T> {
  let lastErr: unknown = null;
  for (let i = 0; i < attempts; i++) {
    onAttempt?.(i + 1);
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      if (i === attempts - 1) break;
      const delay = base * 2 ** i;
      await new Promise((res) => setTimeout(res, delay));
    }
  }
  toast.error("Failed to reach backend");
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

export default retry;
