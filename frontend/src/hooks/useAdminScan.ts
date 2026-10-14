import { useCallback, useEffect, useRef, useState } from 'react';
import type { AdminScan } from '../api';

/** How often an admin page re-polls while the backend's startup warm-up is still running. */
export const ADMIN_WARMING_POLL_MS = 3_000;

/**
 * Loads an admin scan (Data Admin, Instrument Admin, Data Quality) and, while
 * the backend says its startup warm-up is still running, re-polls every
 * {@link ADMIN_WARMING_POLL_MS} so the partial list fills in on its own (#10754).
 *
 * `onData` receives every result with its `warming` flag, so a page can merge
 * it into local state (e.g. keep unsaved edits, and rows a partial result does
 * not include yet) instead of replacing it. `reload` starts a fresh load, e.g.
 * after a save.
 */
export function useAdminScan<T>(
  load: () => Promise<AdminScan<T>>,
  onData: (data: T, warming: boolean) => void,
  onError: (error: unknown) => void
): { warming: boolean; reload: () => void } {
  const [warming, setWarming] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // Latest callbacks without re-running the load whenever a page re-renders.
  const callbacks = useRef({ load, onData, onError });
  useEffect(() => {
    callbacks.current = { load, onData, onError };
  });

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Via Promise.resolve so a loader that throws synchronously lands in onError.
    Promise.resolve()
      .then(() => callbacks.current.load())
      .then(
        (result) => {
          if (cancelled) return;
          callbacks.current.onData(result.data, result.warming);
          setWarming(result.warming);
          if (result.warming) {
            timer = setTimeout(
              () => setAttempt((n) => n + 1),
              ADMIN_WARMING_POLL_MS
            );
          }
        },
        (error: unknown) => {
          if (cancelled) return;
          setWarming(false);
          callbacks.current.onError(error);
        }
      );
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { warming, reload };
}
