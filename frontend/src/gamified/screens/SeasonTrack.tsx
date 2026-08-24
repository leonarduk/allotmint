import { useMemo } from 'react';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  buildSeasonGoals,
  seasonCountdown,
  type SeasonGoal,
} from '../seasonModel';
import Meter from '../components/Meter';

function GoalRow({ goal }: { goal: SeasonGoal }) {
  return (
    <li
      className={`${styles.choreRow} ${goal.complete ? styles.choreRowDone : ''}`}
    >
      <div className={styles.choreBody}>
        <div
          className={`${styles.choreTitle} ${
            goal.complete ? styles.choreTitleDone : ''
          }`}
        >
          {goal.title}
        </div>
        <div className={styles.goalMeter}>
          <Meter
            pct={goal.pct}
            label={`${goal.title}: ${goal.display} so far`}
          />
          <span className={styles.goalValue}>{goal.display}</span>
        </div>
      </div>
      <span
        className={styles.choreReward}
        title={goal.complete ? `${goal.rewardLabel} earned` : goal.rewardLabel}
      >
        <span aria-hidden="true">{goal.rewardIcon}</span>
        {goal.complete ? 'Earned' : goal.rewardLabel}
      </span>
    </li>
  );
}

/**
 * The season ladder: tiered milestones over the real UK tax year, with the
 * countdown to 5 April that actually matters for unused allowances.
 *
 * `now` comes from the render rather than a prop because the countdown only
 * needs to be right to the hour; `seasonCountdown` itself is pure and takes
 * the clock as an argument so it stays testable.
 */
export default function SeasonTrack() {
  const { snapshot, allowances, season } = usePlotData();

  const goals = useMemo(
    () => buildSeasonGoals(snapshot, allowances),
    [snapshot, allowances]
  );

  const countdown = useMemo(
    () => (season ? seasonCountdown(season, new Date()) : null),
    [season]
  );

  const done = goals.filter((goal) => goal.complete).length;
  const groups = useMemo(() => {
    const byGroup = new Map<string, SeasonGoal[]>();
    for (const goal of goals) {
      const bucket = byGroup.get(goal.group) ?? [];
      bucket.push(goal);
      byGroup.set(goal.group, bucket);
    }
    return [...byGroup.entries()];
  }, [goals]);

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {season ? `Growing season ${season.label}` : 'Growing season'} ({done}
          /{goals.length})
        </h2>
        {countdown ? (
          <p className={styles.seasonCountdown}>{countdown.label}</p>
        ) : (
          <p className={styles.sectionNote}>
            No tax year reported for this grower, so the season has no end date
            to count down to.
          </p>
        )}
        <p className={styles.sectionNote}>
          The season is the UK tax year (6 April to 5 April) reported by the
          allowances API — the date unused ISA and pension headroom expires.
        </p>
      </section>

      {groups.map(([group, groupGoals]) => (
        <section key={group} className={`${styles.panel} ${styles.panelGlow}`}>
          <h3 className={styles.panelTitle}>
            {group} ({groupGoals.filter((goal) => goal.complete).length}/
            {groupGoals.length})
          </h3>
          <ul className={styles.plainList}>
            {groupGoals.map((goal) => (
              <GoalRow key={goal.id} goal={goal} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
