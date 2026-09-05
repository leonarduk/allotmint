import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import errorToast from "../utils/errorToast";
import {
  isFresh,
  readFetchCache,
  runDeduped,
  writeFetchCache,
  type FetchCacheEntry,
} from "../utils/fetchCache";

/** Default staleness window for cached results, used when no `ttlMs` is given. */
export const DEFAULT_FETCH_TTL_MS = 60_000;

export type UseFetchOptions = {
  /**
   * Opt in to the cross-unmount result cache. The key must already fold in
   * everything `fn` varies on (the same values you pass in `deps`) -- e.g.
   * `` `portfolio-group:${slug}:${asOf ?? ""}` ``. Omit it and the hook keeps
   * its original fetch-on-every-mount behaviour.
   */
  cacheKey?: string | null;
  /**
   * How long a cached value is served without going to the network. Past this
   * the value is still rendered immediately, but a revalidation runs behind it.
   */
  ttlMs?: number;
};

type State<T> = {
  data: T | null;
  loading: boolean;
  error: Error | null;
};

const IDLE: State<never> = { data: null, loading: false, error: null };

const initialState = <T,>(
  cacheKey: string | null,
  enabled: boolean,
): State<T> => {
  if (!enabled) return IDLE as State<T>;
  const cached = cacheKey ? readFetchCache<T>(cacheKey) : undefined;
  if (!cached) return { data: null, loading: true, error: null };
  // A cached value is on screen from the very first commit, so a remount never
  // flashes a skeleton for data we already hold. `loading` stays false even
  // when a revalidation is about to run: callers gate their skeletons on it and
  // would blank the page again if it were true.
  return { data: cached.value, loading: false, error: null };
};

/**
 * Small helper hook that wraps an async function and provides
 * the resolved `data`, a `loading` indicator and any `error`.
 *
 * It automatically re-runs whenever `enabled`, `fn` or the dependency list
 * changes and will reset its state when `enabled` is set to `false`.
 *
 * Callers should ensure that `fn` and values in `deps` are memoized (e.g. via
 * `useCallback`/`useMemo`) so the dependency array only changes when inputs do.
 *
 * Pass `options.cacheKey` to keep results across unmount and serve them
 * stale-while-revalidate: a remount renders the cached value immediately and
 * only goes to the network once the value is older than `options.ttlMs`. See
 * `utils/fetchCache.ts` for why this exists. Without a `cacheKey` nothing is
 * cached and the hook behaves exactly as it did before.
 */
export function useFetch<T>(
  fn: () => Promise<T>,
  deps: DependencyList = [],
  enabled = true,
  options: UseFetchOptions = {}
) {
  const { cacheKey = null, ttlMs = DEFAULT_FETCH_TTL_MS } = options;

  const [state, setState] = useState<State<T>>(() =>
    initialState<T>(cacheKey, enabled),
  );
  const [refreshVersion, setRefreshVersion] = useState(0);
  // Set by `refetch` so the next effect run skips the freshness check and the
  // in-flight share. A ref, not state: it is read by the effect that
  // `refreshVersion` already triggers, and must not schedule a render itself.
  const forceRef = useRef(false);
  const refetch = useCallback(() => {
    forceRef.current = true;
    setRefreshVersion((version) => version + 1);
  }, []);

  // Adjusting state during render -- React's documented pattern for "an input
  // changed and the current state is now wrong" -- rather than in an effect: a
  // new cache key has to take effect on this commit, or the previous key's
  // value renders for a frame (the old group's holdings after a group switch).
  const [tracked, setTracked] = useState({ cacheKey, enabled });
  if (tracked.cacheKey !== cacheKey || tracked.enabled !== enabled) {
    setTracked({ cacheKey, enabled });
    setState(initialState<T>(cacheKey, enabled));
  }

  useEffect(() => {
    if (!enabled) return;

    const force = forceRef.current;
    forceRef.current = false;

    let cached: FetchCacheEntry<T> | undefined;
    if (cacheKey && !force) {
      cached = readFetchCache<T>(cacheKey);
      // Fresh enough: render what `initialState` already put on screen and make
      // no request at all. This is the case that makes coming back to a page
      // instant instead of a second cold load.
      if (cached && isFresh(cached, ttlMs)) return;
    }

    let cancelled = false;
    if (!cached) {
      setState({ data: null, loading: true, error: null });
    }

    (async () => {
      try {
        // A forced refetch bypasses the in-flight share so it can't be answered
        // by a call that started before the user asked for fresh data, but its
        // result still lands in the cache for everyone else.
        let res: T;
        if (cacheKey && !force) {
          res = await runDeduped(cacheKey, fn);
        } else {
          res = await fn();
          if (cacheKey) writeFetchCache(cacheKey, res);
        }
        if (!cancelled) setState({ data: res, loading: false, error: null });
      } catch (e) {
        if (cancelled) return;
        const err = e instanceof Error ? e : new Error(String(e));
        if (cached) {
          // Background revalidation of data that is already on screen. Callers
          // treat `error` as "replace the page with a retry prompt"
          // (GroupPortfolioView.tsx:797), so surfacing this would throw away a
          // perfectly good rendered page because its silent refresh failed.
          // Keep the stale value, stay quiet, and let the next explicit refresh
          // -- which forces, and so takes the branch below -- report it.
          console.warn(`Background revalidation failed for ${cacheKey}`, err);
          return;
        }
        setState({ data: null, loading: false, error: err });
        errorToast(err);
      }
    })();

    return () => {
      cancelled = true;
    };
  },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [enabled, cacheKey, ttlMs, fn, refreshVersion, ...deps]);

  return { data: state.data, loading: state.loading, error: state.error, refetch };
}

export default useFetch;
