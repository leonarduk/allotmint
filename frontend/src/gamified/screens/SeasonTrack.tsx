import { useMemo } from 'react';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import { ALLOWANCES_UNAVAILABLE_MESSAGE } from '../plotModel';
import {
  buildSeasonGroups,
  seasonCountdown,
  type SeasonGroupProgress,
} from '../seasonModel';
import Meter from '../components/Meter';

/**
 * One row per category, tracking progress toward the next tier that has not
 * been earned yet. Earlier tiers already earned collapse into a compact
 * badge instead of each repeating the same current value against a target
 * that's already been cleared — see #7006.
 */
function GroupRow({ group }: { group: SeasonGroupProgress }) {
  return (
    <li
      className={`${styles.choreRow} ${
        group.complete ? styles.choreRowDone : ''
      }`}
    >
      <div className={styles.choreBody}>
        <div
          className={`${styles.choreTitle} ${
            group.complete ? styles.choreTitleDone : ''
          }`}
        >
          {group.unavailable
            ? group.group
            : group.complete
              ? `Every ${group.group} tier earned`
              : group.next?.title}
        </div>

        {group.unavailable ? (
          <p className={styles.sectionNote}>{ALLOWANCES_UNAVAILABLE_MESSAGE}</p>
        ) : group.next ? (
          <div className={styles.groupProgress}>
            <div className={styles.goalMeter}>
              <Meter
                pct={group.next.pct}
                label={`${group.group}: ${group.currentDisplay} of ${group.next.displayTarget} toward the next tier`}
              />
              <span className={styles.goalValue}>
                {group.currentDisplay} / {group.next.displayTarget}
              </span>
            </div>
            <p className={styles.groupCurrent}>
              Currently at <strong>{group.currentDisplay}</strong>.
            </p>
          </div>
        ) : (
          <p className={styles.groupComplete}>
            {group.currentDisplay} — every tier in this category is earned.
          </p>
        )}

        {!group.unavailable && (
          <ul className={styles.tierRow}>
            {group.tiers.map((tier) => {
              const isNext =
                !tier.complete && group.next?.target === tier.target;
              return (
                <li
                  key={tier.target}
                  className={`${styles.tierBadge} ${
                    tier.complete
                      ? styles.tierBadgeEarned
                      : isNext
                        ? styles.tierBadgeNext
                        : ''
                  }`}
                >
                  {tier.complete ? '✓ ' : ''}
                  {tier.displayTarget}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <span
        className={styles.choreReward}
        title={
          group.complete ? `${group.rewardLabel} earned` : group.rewardLabel
        }
      >
        <span aria-hidden="true">{group.rewardIcon}</span>
        {group.complete ? 'Earned' : group.rewardLabel}
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
  const { snapshot, allowances, allowancesUnavailable, season } =
    usePlotData();

  const groups = useMemo(
    () => buildSeasonGroups(snapshot, allowances, allowancesUnavailable),
    [snapshot, allowances, allowancesUnavailable]
  );

  const countdown = useMemo(
    () => (season ? seasonCountdown(season, new Date()) : null),
    [season]
  );

  const totalTiers = groups.reduce(
    (sum, group) => sum + group.tiers.length,
    0
  );
  const earnedTiers = groups.reduce(
    (sum, group) => sum + group.tiers.filter((tier) => tier.complete).length,
    0
  );

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {season ? `Growing season ${season.label}` : 'Growing season'} (
          {earnedTiers}/{totalTiers})
        </h2>
        {countdown ? (
          <p className={styles.seasonCountdown}>{countdown.label}</p>
        ) : allowancesUnavailable ? (
          <p className={styles.sectionNote}>{ALLOWANCES_UNAVAILABLE_MESSAGE}</p>
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

      {groups.map((group) => (
        <section
          key={group.id}
          className={`${styles.panel} ${styles.panelGlow}`}
        >
          <h3 className={styles.panelTitle}>
            {group.group} (
            {group.tiers.filter((tier) => tier.complete).length}/
            {group.tiers.length})
          </h3>
          <ul className={styles.plainList}>
            <GroupRow group={group} />
          </ul>
        </section>
      ))}
    </div>
  );
}
