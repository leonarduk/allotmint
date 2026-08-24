import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { cropGlyph } from '../cropGlyph';
import type { GerminatingCrop } from '../plotModel';
import Meter from './Meter';

interface PropagatorProps {
  entries: readonly GerminatingCrop[];
  basePath: string;
}

/**
 * Crops still serving their minimum holding period, shown as trays in a
 * propagator. The progress and the ready date are the backend's own
 * `days_until_eligible` / `next_eligible_sell_date`, so this doubles as a
 * plain-English read of when each holding becomes sellable.
 */
export default function Propagator({ entries, basePath }: PropagatorProps) {
  if (entries.length === 0) {
    return (
      <p className={styles.sectionNote}>
        Nothing in the propagator — every crop has served its holding period and
        can be lifted.
      </p>
    );
  }

  return (
    <>
      <div className={styles.trayGrid}>
        {entries.map(({ crop, pct, daysHeld, daysRemaining, readyOn }) => (
          <Link
            key={crop.ticker}
            to={`${basePath}/crops/${encodeURIComponent(crop.ticker)}`}
            className={styles.tray}
          >
            <span className={styles.trayGlyph} aria-hidden="true">
              {cropGlyph(crop.ticker, crop.sector)}
            </span>
            <span className={styles.trayTicker}>{crop.ticker}</span>
            <Meter
              pct={pct}
              tone="water"
              label={`${crop.ticker}: ${daysHeld} days held, ${daysRemaining} to go`}
            />
            <span className={styles.trayDays}>
              {daysHeld} / {daysHeld + daysRemaining} days
            </span>
            <span className={styles.trayReady}>
              {readyOn ? `Ready ${readyOn}` : `${daysRemaining} days to go`}
            </span>
          </Link>
        ))}
      </div>
      <p className={styles.sectionNote}>
        Progress toward each holding&apos;s minimum holding period, from the
        same rule the classic compliance screens use.
      </p>
    </>
  );
}
