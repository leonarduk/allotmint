import type { DayStamp } from '../gamified/seasonModel';

/**
 * The subset of a CSS-module class map these helpers need. CSS modules are
 * typed as an index signature (`{ [key: string]: string }`), so we cannot
 * require named keys statically — the helpers only ever read the four keys
 * below, and the component's stylesheet is the source of truth for them.
 */
export interface StampStyles {
  readonly [key: string]: string;
}

/**
 * The class for a single day's stamp disc. `total > 0` means the Trail has a
 * real record for the day and it just was not finished — that is a genuine
 * miss. `total === 0` means the backend has no record at all (before
 * tracking began, or not used that day). The two used to render identically
 * (#7204); give the untracked one the plain dashed/hollow `.stamp` look and
 * the missed one a solid, clearly-empty disc.
 */
export function stampClass(day: DayStamp, styles: StampStyles): string {
  if (day.stamped) return `${styles.stamp} ${styles.stampDone}`;
  if (day.partial) return `${styles.stamp} ${styles.stampPartial}`;
  if (day.total > 0) return `${styles.stamp} ${styles.stampMissed}`;
  return styles.stamp;
}

/**
 * The crate goal caption and open/closed state. Untracked days (no Trail
 * record) must never count against the grower — a user on their first
 * tracked day should read "1 of 7 days down", not "6 to go and you've
 * already lost" (#7204). Only once the whole window has real records does a
 * miss mean anything.
 */
export function crateState(days: readonly DayStamp[]): {
  open: boolean;
  label: string;
} {
  const tracked = days.filter((day) => day.total > 0);
  const fullyDone = tracked.filter((day) => day.stamped).length;

  if (tracked.length === 0) {
    return { open: false, label: 'No chores tracked yet this week' };
  }

  if (tracked.length < days.length) {
    // Still early in the tracked history: the untracked days before it
    // started are not misses. Count a day mid-progress (some chores done,
    // not all) toward "down" too — a user two chores into today has not
    // failed today, so it must not silently collapse into the same "0" a
    // day with zero activity would show.
    const engaged = tracked.filter((day) => day.stamped || day.partial).length;
    return {
      open: false,
      label: `${engaged} of ${days.length} day${days.length === 1 ? '' : 's'} down — keep going to fill the crate`,
    };
  }

  return fullyDone === tracked.length
    ? { open: true, label: 'Full week of chores done' }
    : { open: false, label: 'Finish every day this week to fill the crate' };
}
