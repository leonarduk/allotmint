import { useCallback, useMemo, useState } from 'react';

/**
 * Per-item pending/error state for async operations on a list of items,
 * keyed by id.
 *
 * Several items may be in flight, or in an error state, at the same time
 * (e.g. the user clicks chore A and then chore B before A settles), so the
 * hook tracks a *set* of pending ids and a *set* of errored ids. A transition
 * for one id never touches another id's state.
 *
 * Callers drive it through four transitions:
 *
 *   start(id)   — a request for `id` is now in flight (clears any prior error
 *                 for the same id, so a retry doesn't show a stale message)
 *   succeed(id) — the request for `id` resolved; clears pending and error
 *   fail(id)    — the request for `id` rejected; clears pending, records error
 *   reset(id)   — clear both pending and error for `id` without a transition
 *
 * The hook does not store the error *message* — only which ids errored. That
 * keeps it generic (callers own their own copy/formatting) and avoids baking
 * a string shape into the hook's API.
 */
export interface AsyncItemState {
  /** Ids whose async operation is currently in flight. */
  pendingIds: ReadonlySet<string>;
  /** Ids whose most recent async operation failed. */
  errorIds: ReadonlySet<string>;
  /** Mark `id` as in flight. Clears any prior error for the same id. */
  start: (id: string) => void;
  /** Mark `id` as settled successfully. Clears pending and error for `id`. */
  succeed: (id: string) => void;
  /** Mark `id` as failed. Clears pending and records `id` as errored. */
  fail: (id: string) => void;
  /** Clear pending and error for `id` without recording a transition. */
  reset: (id: string) => void;
}

function withId(prev: ReadonlySet<string>, id: string): ReadonlySet<string> {
  if (prev.has(id)) return prev;
  return new Set(prev).add(id);
}

function withoutId(
  prev: ReadonlySet<string>,
  id: string
): ReadonlySet<string> {
  if (!prev.has(id)) return prev;
  const next = new Set(prev);
  next.delete(id);
  return next;
}

/**
 * Manage per-item pending/error state for a list of async operations.
 *
 * See {@link AsyncItemState} for the transition semantics. The returned
 * callbacks are stable across renders, so they can be safely used in
 * dependency arrays (e.g. inside `useCallback`).
 */
export function useAsyncItemState(): AsyncItemState {
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(
    () => new Set()
  );
  const [errorIds, setErrorIds] = useState<ReadonlySet<string>>(
    () => new Set()
  );

  const start = useCallback((id: string) => {
    setPendingIds((prev) => withId(prev, id));
    // A retry should not keep showing the previous failure for the same row.
    setErrorIds((prev) => withoutId(prev, id));
  }, []);

  const succeed = useCallback((id: string) => {
    setPendingIds((prev) => withoutId(prev, id));
    setErrorIds((prev) => withoutId(prev, id));
  }, []);

  const fail = useCallback((id: string) => {
    setPendingIds((prev) => withoutId(prev, id));
    setErrorIds((prev) => withId(prev, id));
  }, []);

  const reset = useCallback((id: string) => {
    setPendingIds((prev) => withoutId(prev, id));
    setErrorIds((prev) => withoutId(prev, id));
  }, []);

  return useMemo(
    () => ({ pendingIds, errorIds, start, succeed, fail, reset }),
    [pendingIds, errorIds, start, succeed, fail, reset]
  );
}

export default useAsyncItemState;
