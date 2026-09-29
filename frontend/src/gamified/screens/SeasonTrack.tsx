import { useMemo } from 'react';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import { ALLOWANCES_UNAVAILABLE_MESSAGE } from '../plotModel';
import {
  buildSeasonBadges,
  buildSeasonGroups,
  seasonCountdown,
  type SeasonBadge,
  type SeasonGroupProgress,
} from '../seasonModel';
import Meter from '../components/Meter';

/**
 * One row per category, tracking progress toward the next tier that has not
 * been earned yet. Earlier tiers already earned collapse into a compact
 * badge instead of each repeating the same current value against a target
 * that's already been cleared — see #7006.
 *
 * The goal line is the ladder's own `title(target)` ("Tend 25 crops at
 * once"), not a bare "Next: 25" — the description already existed in
 * `buildGoalGroups` and was simply never rendered here (#7194).
 */
function GroupRow({ group }: { group: SeasonGroupProgress }) {
  const capped = group.next !== null && group.next.pct >= 100;

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
            {capped && (
              <p className={styles.groupComplete}>
                {group.currentDisplay} — already past this tier.
              </p>
            )}
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
 * The trophy shelf: one badge per category, earned once every tier in that
 * category is cleared. Derived from the same tier state as the ladder below,
 * so a badge can never claim something the tier chips contradict.
 */
function BadgeShelf({ badges }: { badges: SeasonBadge[] }) {
  const earned = badges.filter((badge) => badge.earned).length;

  return (
    <section className={`${styles.panel} ${styles.panelGlow}`}>
      <h3 className={styles.panelTitle}>
        Badge shelf ({earned}/{badges.length})
      </h3>
      <ul className={styles.badgeShelf}>
        {badges.map((badge) => (
          <li
            key={badge.id}
            className={`${styles.badgeCard} ${
              badge.earned ? styles.badgeCardEarned : ''
            }`}
            title={
              badge.earned
                ? `${badge.rewardLabel} earned`
                : badge.nextTitle ?? badge.rewardLabel
            }
          >
            <span className={styles.badgeIcon} aria-hidden="true">
              {badge.rewardIcon}
            </span>
            <span className={styles.badgeLabel}>{badge.rewardLabel}</span>
            <span className={styles.badgeProgress}>
              {badge.earned ? 'Earned' : badge.progress}
            </span>
          </li>
        ))}
      </ul>
      <p className={styles.sectionNote}>
        A badge is earned when every tier in its category is cleared.
      </p>
    </section>
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

  const badges = useMemo(() => buildSeasonBadges(groups), [groups]);

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

      <BadgeShelf badges={badges} />

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
