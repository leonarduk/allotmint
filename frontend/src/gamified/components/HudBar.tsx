import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { formatGbp, type PlotSnapshot } from '../plotModel';
import Meter from './Meter';

interface HudBarProps {
  snapshot: PlotSnapshot;
  /** Where the "classic view" escape hatch points. */
  classicPath: string;
  /**
   * Badges earned on the season ladder, derived from the same tier state the
   * Season page renders. Optional so the HUD still works where the season
   * data is not loaded.
   */
  badgesEarned?: number;
  badgesTotal?: number;
}

/**
 * Top status strip: plot value, running gain, grower level and XP — the
 * gamified read-out of figures the classic dashboard shows as a table.
 *
 * Plot value and gain belong to the selected grower. Level, rank, XP and
 * streak come from `/trail`, which is the signed-in user's progress and is
 * not owner-scoped, so they sit in their own "Your progress" group rather
 * than reading as an attribute of whichever grower's plot is on screen
 * (#7191).
 */
export default function HudBar({
  snapshot,
  classicPath,
  badgesEarned = 0,
  badgesTotal = 0,
}: HudBarProps) {
  const { t } = useTranslation();
  const { grower, plotValueGbp, totalGainGbp, streak, rank } = snapshot;
  const gainClass = totalGainGbp >= 0 ? styles.hudChipGain : styles.hudChipLoss;
  // Built as one string rather than interpolated JSX children so it lands in
  // the DOM as a single text node (readable by screen readers and testable).
  const xpLabel = t('plot.hud.xpLabel', {
    level: grower.level,
    xp: grower.xpIntoLevel,
    xpForLevel: grower.xpForLevel,
  });

  return (
    <header className={styles.hud}>
      <h1 className={styles.hudTitle}>
        {t('plot.hud.title')}
      </h1>

      <div className={styles.hudSpacer} />

      <span className={styles.hudChip} title={t('plot.hud.plotValueTitle')}>
        <span aria-hidden="true">🧺</span>
        <span>{formatGbp(plotValueGbp)}</span>
        <span className={styles.srOnly}>{t('plot.hud.plotValueSr')}</span>
      </span>

      <span
        className={`${styles.hudChip} ${gainClass}`}
        title={t('plot.hud.gainTitle')}
      >
        <span aria-hidden="true">{totalGainGbp >= 0 ? '🌿' : '🥀'}</span>
        <span>{formatGbp(totalGainGbp)}</span>
        <span className={styles.srOnly}>{t('plot.hud.gainSr')}</span>
      </span>

      {badgesTotal > 0 && (
        <span
          className={styles.hudChip}
          title={t('plot.hud.badgesTitle')}
        >
          <span aria-hidden="true">🏅</span>
          <span>
            {badgesEarned}/{badgesTotal}
          </span>
          <span className={styles.srOnly}>{t('plot.hud.badgesSr')}</span>
        </span>
      )}

      <div
        className={styles.hudProgress}
        role="group"
        aria-label={t('plot.hud.progressLabel')}
        title={t('plot.hud.progressTitle')}
      >
        <span className={styles.hudProgressLabel}>
          <span>{t('plot.hud.progressLabel')}</span>
          <span className={styles.hudRank}>{rank}</span>
        </span>

        {streak > 0 && (
          <span
            className={styles.hudChip}
            title={t('plot.hud.streakTitle')}
          >
            <span aria-hidden="true">🔥</span>
            <span>{streak}</span>
            <span className={styles.srOnly}>{t('plot.hud.streakSr')}</span>
          </span>
        )}

        <div className={styles.hudLevel}>
          <span className={styles.hudLevelBadge} aria-hidden="true">
            {grower.level}
          </span>
          <div className={styles.hudXp}>
            <span className={styles.hudXpLabel}>{xpLabel}</span>
            <Meter
              pct={grower.pct}
              label={t('plot.hud.meterLabel', {
                level: grower.level,
                xp: grower.xpIntoLevel,
                xpForLevel: grower.xpForLevel,
              })}
            />
          </div>
        </div>
      </div>

      <Link className={styles.ghostButton} to={classicPath}>
        <span aria-hidden="true">📊</span>
        {t('plot.hud.classicView')}
      </Link>
    </header>
  );
}
