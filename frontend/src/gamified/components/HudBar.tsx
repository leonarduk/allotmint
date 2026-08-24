import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { formatGbp, type PlotSnapshot } from '../plotModel';
import Meter from './Meter';

interface HudBarProps {
  snapshot: PlotSnapshot;
  /** Where the "classic view" escape hatch points. */
  classicPath: string;
}

/**
 * Top status strip: plot value, running gain, grower level and XP — the
 * gamified read-out of figures the classic dashboard shows as a table.
 */
export default function HudBar({ snapshot, classicPath }: HudBarProps) {
  const { grower, plotValueGbp, totalGainGbp, streak, rank } = snapshot;
  const gainClass = totalGainGbp >= 0 ? styles.hudChipGain : styles.hudChipLoss;
  // Built as one string rather than interpolated JSX children so it lands in
  // the DOM as a single text node (readable by screen readers and testable).
  const xpLabel = `Level ${grower.level} · ${grower.xpIntoLevel}/${grower.xpForLevel} XP`;

  return (
    <header className={styles.hud}>
      <h1 className={styles.hudTitle}>
        <span>The Plot</span>
        <span className={styles.hudRank}>{rank}</span>
      </h1>

      <div className={styles.hudSpacer} />

      <span className={styles.hudChip} title="Total plot value">
        <span aria-hidden="true">🧺</span>
        <span>{formatGbp(plotValueGbp)}</span>
        <span className={styles.srOnly}>total plot value</span>
      </span>

      <span
        className={`${styles.hudChip} ${gainClass}`}
        title="Unrealised gain across every bed"
      >
        <span aria-hidden="true">{totalGainGbp >= 0 ? '🌿' : '🥀'}</span>
        <span>{formatGbp(totalGainGbp)}</span>
        <span className={styles.srOnly}>unrealised gain</span>
      </span>

      {streak > 0 && (
        <span
          className={styles.hudChip}
          title="Consecutive days of chores done"
        >
          <span aria-hidden="true">🔥</span>
          <span>{streak}</span>
          <span className={styles.srOnly}>day streak</span>
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
            label={`Grower level ${grower.level}, ${grower.xpIntoLevel} of ${grower.xpForLevel} XP to the next level`}
          />
        </div>
      </div>

      <Link className={styles.ghostButton} to={classicPath}>
        <span aria-hidden="true">📊</span>
        Classic view
      </Link>
    </header>
  );
}
