import { useCallback, useState } from 'react';

/**
 * State for a single in-flight async operation on a list item, keyed by id.
 *
 * The hook intentionally tracks only *one* pending id and *one* error id at a
 * time. That matches the common UI pattern where a list of items each have an
 * action button, but only one action can meaningfully be in flight or in an
 * error state per row at once — and it keeps the state machine small enough to
 * reason about (no partially-applied transitions, no stale ids).
 *
 * Callers are expected to drive it through the four transitions:
 *
 *   start(id)   — a request for `id` is now in flight (clears any prior error
 *                 for the same id, so a retry doesn't show a stale message)
 *   succeed(id) — the request for `id` resolved; clears pending (and error)
 *   fail(id)    — the request for `id` rejected; clears pending, records error
 *   reset(id)   — clear both pending and error for `id` without a transition
 *
 * The hook does not store the error *message* — only which id errored. That
 * keeps it generic (callers own their own copy/formatting) and avoids baking
 * a string shape into the hook's API.
 */
export interface AsyncItemState {
  /** The id whose async operation is currently in flight, if any. */
  pendingId: string | null;
  /** The id whose most recent async operation failed, if any. */
  errorId: string | null;
  /** Mark `id` as in flight. Clears any prior error for the same id. */
  start: (id: string) => void;
  /** Mark `id` as settled successfully. Clears pending and error for `id`. */
  succeed: (id: string) => void;
  /** Mark `id` as failed. Clears pending and records `id` as the error. */
  fail: (id: string) => void;
  /** Clear pending and error for `id` without recording a transition. */
  reset: (id: string) => void;
}

/**
 * Manage per-item pending/error state for a list of async operations.
 *
 * See {@link AsyncItemState} for the transition semantics. The returned
 * callbacks are stable across renders, so they can be safely used in
 * dependency arrays (e.g. inside `useCallback`).
 */
export function useAsyncItemState(): AsyncItemState {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);

  const start = useCallback((id: string) => {
    setPendingId(id);
    // A retry should not keep showing the previous failure for the same row.
    setErrorId((prev) => (prev === id ? null : prev));
  }, []);

  const succeed = useCallback((id: string) => {
    setPendingId((prev) => (prev === id ? null : prev));
    setErrorId((prev) => (prev === id ? null : prev));
  }, []);

  const fail = useCallback((id: string) => {
    setPendingId((prev) => (prev === id ? null : prev));
    setErrorId(id);
  }, []);

  const reset = useCallback((id: string) => {
    setPendingId((prev) => (prev === id ? null : prev));
    setErrorId((prev) => (prev === id ? null : prev));
  }, []);

  return { pendingId, errorId, start, succeed, fail, reset };
}

export default useAsyncItemState;
