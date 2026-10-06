import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import styles from '../plot.module.css';
import type { DayStamp } from '../seasonModel';
import { crateState, stampClass } from '@/utils/crateProgress';

interface StreakPathProps {
  days: readonly DayStamp[];
  streak: number;
}

function stampLabel(day: DayStamp, t: TFunction): string {
  if (day.total === 0) return t('plot.streak.noChores', { date: day.date });
  return t('plot.streak.choresDone', {
    date: day.date,
    completed: day.completed,
    total: day.total,
  });
}

/**
 * A week of chore history as stamped discs, with the reward crate at the end.
 * Each disc reflects a real per-day total from the Trail: done, missed
 * (tracked but not finished), or untracked (no Trail record at all). Days
 * the backend has no record for stay visually distinct from a real miss
 * rather than reading as one (#7204).
 */
export default function StreakPath({ days, streak }: StreakPathProps) {
  const { t } = useTranslation();
  if (days.length === 0) return null;
  const crate = crateState(days);

  return (
    <div className={styles.streakPath}>
      <ol
        className={styles.stampRow}
        aria-label={t('plot.streak.ariaLabel')}
      >
        {days.map((day) => (
          <li key={day.date} className={styles.stampCell}>
            <span className={stampClass(day, styles)} title={stampLabel(day, t)}>
              <span aria-hidden="true">
                {day.stamped ? '🌿' : day.partial ? '🌱' : ''}
              </span>
              <span className={styles.srOnly}>{stampLabel(day, t)}</span>
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
