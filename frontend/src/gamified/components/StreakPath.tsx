import styles from '../plot.module.css';
import type { DayStamp } from '../seasonModel';

interface StreakPathProps {
  days: readonly DayStamp[];
  streak: number;
}

function stampClass(day: DayStamp): string {
  if (day.stamped) return `${styles.stamp} ${styles.stampDone}`;
  if (day.partial) return `${styles.stamp} ${styles.stampPartial}`;
  // `total > 0` means the Trail has a real record for the day and it just
  // was not finished — that is a genuine miss. `total === 0` means the
  // backend has no record at all (before tracking began, or not used that
  // day). The two used to render identically (#7204); give the untracked
  // one the plain dashed/hollow `.stamp` look and the missed one a solid,
  // clearly-empty disc.
  if (day.total > 0) return `${styles.stamp} ${styles.stampMissed}`;
  return styles.stamp;
}

function stampLabel(day: DayStamp): string {
  if (day.total === 0) return `${day.date}: no chores recorded`;
  return `${day.date}: ${day.completed} of ${day.total} chores done`;
}

/**
 * The crate goal caption and open/closed state. Untracked days (no Trail
 * record) must never count against the grower — a user on their first
 * tracked day should read "1 day down", not "6 to go and you've already
 * lost" (#7204). Only once the whole window has real records does a miss
 * mean anything.
 */
function crateState(days: readonly DayStamp[]): {
  open: boolean;
  label: string;
} {
  const tracked = days.filter((day) => day.total > 0);
  const doneCount = tracked.filter((day) => day.stamped).length;

  if (tracked.length === 0) {
    return { open: false, label: 'No chores tracked yet this week' };
  }

  if (tracked.length < days.length) {
    // Still early in the tracked history: the untracked days before it
    // started are not misses, so don't frame this as "N to go".
    return {
      open: false,
      label: `${doneCount} day${doneCount === 1 ? '' : 's'} down — keep going to fill the crate`,
    };
  }

  return doneCount === tracked.length
    ? { open: true, label: 'Full week of chores done' }
    : { open: false, label: 'Finish every day this week to fill the crate' };
}

/**
 * A week of chore history as stamped discs, with the reward crate at the end.
 * Each disc reflects a real per-day total from the Trail: done, missed
 * (tracked but not finished), or untracked (no Trail record at all). Days
 * the backend has no record for stay visually distinct from a real miss
 * rather than reading as one (#7204).
 */
export default function StreakPath({ days, streak }: StreakPathProps) {
  if (days.length === 0) return null;
  const crate = crateState(days);

  return (
    <div className={styles.streakPath}>
      <ol
        className={styles.stampRow}
        aria-label="Chore history for the last week"
      >
        {days.map((day) => (
          <li key={day.date} className={styles.stampCell}>
            <span className={stampClass(day)} title={stampLabel(day)}>
              <span aria-hidden="true">
                {day.stamped ? '🌿' : day.partial ? '🌱' : ''}
              </span>
              <span className={styles.srOnly}>{stampLabel(day)}</span>
            </span>
            <span
              className={
                day.isToday
                  ? `${styles.stampDay} ${styles.stampDayToday}`
                  : styles.stampDay
              }
              aria-hidden="true"
            >
              {day.initial}
            </span>
          </li>
        ))}
        <li className={styles.stampCell}>
          <span
            className={
              crate.open ? `${styles.crate} ${styles.crateOpen}` : styles.crate
            }
            title={crate.label}
          >
            <span aria-hidden="true">🧺</span>
            <span className={styles.srOnly}>{crate.label}</span>
          </span>
          <span className={styles.stampDay} aria-hidden="true">
            {streak}d
          </span>
        </li>
      </ol>
    </div>
  );
}
