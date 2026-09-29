import { useCallback, useEffect, useRef } from "react";

/**
 * A hook that deduplicates requests by key.
 *
 * The returned `run` function accepts a key and a request thunk. If a request
 * for that key is already in-flight (or has already been requested and not
 * cleared), the call is skipped. The key is added to the internal ref set
 * *before* the request starts, and removed on failure so a subsequent call
 * with the same key will retry. On success the key is retained, which is what
 * suppresses duplicate requests for the same key.
 *
 * The guard is stored in a ref (not state) on purpose: callers frequently
 * invoke `run` multiple times within a single tick (e.g. once per selected
 * owner in a `useEffect`). Once the first call queues a state update, React
 * stops eagerly evaluating later updaters, so anything a later updater
 * computes is not readable at its call site. A ref is readable synchronously
 * and therefore correct for this pattern.
 *
 * @param request A function that performs the request for a given key.
 * @returns An object with `run(key)` to execute a deduped request and
 *          `clear(keys?)` to clear specific keys (or all keys when omitted).
 */
export function useDedupedRequest<T>(
  request: (key: string) => Promise<T>,
): {
  run: (key: string) => Promise<T | undefined>;
  clear: (keys?: Iterable<string>) => void;
} {
  const requestedKeys = useRef<Set<string>>(new Set());
  const requestRef = useRef(request);

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  const run = useCallback(async (key: string): Promise<T | undefined> => {
    if (requestedKeys.current.has(key)) {
      return undefined;
    }
    requestedKeys.current.add(key);
    try {
      return await requestRef.current(key);
    } catch (error) {
      // Drop the key on failure so a subsequent call retries. A successful
      // request keeps the key, which is what suppresses repeat requests.
      requestedKeys.current.delete(key);
      throw error;
    }
  }, []);

  const clear = useCallback((keys?: Iterable<string>) => {
    if (keys === undefined) {
      requestedKeys.current.clear();
      return;
    }
    for (const key of keys) {
      requestedKeys.current.delete(key);
    }
  }, []);

  return { run, clear };
}

export default useDedupedRequest;
