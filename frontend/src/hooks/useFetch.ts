import { useEffect, useState, type DependencyList } from "react";

/**
 * Small helper hook that wraps an async function and provides
 * the resolved `data`, a `loading` indicator and any `error`.
 *
 * It automatically re-runs whenever `enabled`, `fn` or the dependency list
 * changes and will reset its state when `enabled` is set to `false`.
 *
 * Callers should ensure that `fn` is stable (e.g. via `useCallback`) to avoid
 * unnecessary re-renders.
 */
export function useFetch<T>(
  fn: () => Promise<T>,
  deps: DependencyList = [],
  enabled = true
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    fn()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, fn, ...deps]);

  return { data, loading, error };
}

export default useFetch;
