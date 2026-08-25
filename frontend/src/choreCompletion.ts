import { completeTrailTask } from "./api";

/**
 * Trail chore ids that the Plot chores screen no longer self-completes on
 * click (#7003). Instead it navigates to the real classic-app flow and sets
 * a marker here; the destination page consumes the marker once the user has
 * actually done the thing the chore describes (visited the overview,
 * completed a lookup, triggered a report). Ids must match
 * `backend/quests/trail.py`'s `STATIC_DAILY_TASKS`.
 */
export type TrackedChoreId =
  | "check_overview"
  | "research_new_stock"
  | "run_a_report";

const STORAGE_KEY = "allotmint:pendingChore";

/** Set by the chores screen right before navigating away from `/plot/chores`. */
export function markChorePending(choreId: TrackedChoreId): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, choreId);
  } catch {
    // Storage can be unavailable (private browsing); the chore simply stays
    // a manual tickbox in that case rather than blocking navigation.
  }
}

/**
 * Consumes the pending marker if it matches `choreId`, clearing it either
 * way so a stale marker can't complete an unrelated later visit.
 */
function consumePendingChore(choreId: TrackedChoreId): boolean {
  try {
    const pending = sessionStorage.getItem(STORAGE_KEY);
    if (pending !== choreId) return false;
    sessionStorage.removeItem(STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

/**
 * Called by the destination page once the real action behind `choreId` has
 * happened. Best-effort, mirroring PlotDataContext's own `completeChore`: a
 * failed write leaves the chore actionable rather than falsely "done".
 */
export function completeTrackedChore(choreId: TrackedChoreId): void {
  if (!consumePendingChore(choreId)) return;
  void completeTrailTask(choreId).catch(() => {
    // Best-effort completion; see PlotDataContext.completeChore for the
    // same swallow-and-retry-later rationale.
  });
}
