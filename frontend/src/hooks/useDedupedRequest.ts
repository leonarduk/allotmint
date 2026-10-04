import { useCallback, useRef } from "react";

/**
 * A hook that deduplicates requests by key.
 *
 * The returned `run` function accepts a key and a request thunk. If a request
 * for that key is already in-flight (or has already been requested and not
 * cleared), the call is skipped and the thunk is never invoked. The key is
 * added to the internal ref set *before* the thunk runs, and removed on
 * failure so a subsequent call with the same key will retry. On success the
 * key is retained, which is what suppresses duplicate requests for the same
 * key.
 *
 * The dedupe key is deliberately independent of the request arguments: the
 * key is only an identity for the guard (e.g. `"alex::2024-01-01"`), while the
 * thunk closes over whatever arguments the real request needs. Passing the
 * key to the request as an argument previously leaked composite keys into
 * URLs (#8576).
 *
 * The guard is stored in a ref (not state) on purpose: callers frequently
 * invoke `run` multiple times within a single tick (e.g. once per selected
 * owner in a `useEffect`). Once the first call queues a state update, React
 * stops eagerly evaluating later updaters, so anything a later updater
 * computes is not readable at its call site. A ref is readable synchronously
 * and therefore correct for this pattern.
 *
 * @returns An object with `run(key, thunk)` to execute a deduped request and
 *          `clear(keys?)` to clear specific keys (or all keys when omitted).
 */
export function useDedupedRequest<T>(): {
  run: (key: string, thunk: () => Promise<T>) => Promise<T | undefined>;
  clear: (keys?: Iterable<string>) => void;
} {
  const requestedKeys = useRef<Set<string>>(new Set());

  const run = useCallback(
    async (key: string, thunk: () => Promise<T>): Promise<T | undefined> => {
      if (requestedKeys.current.has(key)) {
        return undefined;
      }
      requestedKeys.current.add(key);
      try {
        return await thunk();
      } catch (error) {
        // Drop the key on failure so a subsequent call retries. A successful
        // request keeps the key, which is what suppresses repeat requests.
        requestedKeys.current.delete(key);
        throw error;
      }
    },
    [],
  );

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
