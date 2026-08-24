import styles from '../plot.module.css';
import type { DayStamp } from '../seasonModel';

interface StreakPathProps {
  days: readonly DayStamp[];
  streak: number;
}

function stampClass(day: DayStamp): string {
  if (day.stamped) return `${styles.stamp} ${styles.stampDone}`;
  if (day.partial) return `${styles.stamp} ${styles.stampPartial}`;
  return styles.stamp;
}

function stampLabel(day: DayStamp): string {
  if (day.total === 0) return `${day.date}: no chores recorded`;
  return `${day.date}: ${day.completed} of ${day.total} chores done`;
}

/**
 * A week of chore history as stamped discs, with the reward crate at the end.
 * Each disc reflects a real per-day total from the Trail; days the backend
 * has no record for stay blank rather than being filled in.
 */
export default function StreakPath({ days, streak }: StreakPathProps) {
  if (days.length === 0) return null;
  const fullWeek = days.every((day) => day.stamped);

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
              fullWeek ? `${styles.crate} ${styles.crateOpen}` : styles.crate
            }
            title={
              fullWeek
                ? 'Full week of chores done'
                : 'Finish every day this week to fill the crate'
            }
          >
            <span aria-hidden="true">🧺</span>
            <span className={styles.srOnly}>
              {fullWeek
                ? 'Full week of chores done'
                : 'Finish every day this week to fill the crate'}
            </span>
          </span>
          <span className={styles.stampDay} aria-hidden="true">
            {streak}d
          </span>
        </li>
      </ol>
    </div>
  );
}
