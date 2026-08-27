import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import type { GerminatingCrop } from '../plotModel';
import Meter from './Meter';
import CropGlyph from './CropGlyph';

interface PropagatorProps {
  entries: readonly GerminatingCrop[];
  basePath: string;
}

/**
 * Crops still serving their minimum holding period, shown as trays in a
 * propagator. Membership is `sell_eligible: false`, full stop (#7184).
 * Where the backend also gives a known, positive `days_until_eligible` /
 * `next_eligible_sell_date`, the tray shows real progress and a real ready
 * date; where it doesn't, `indeterminate` is true and the tray reads "not
 * yet liftable" with an empty bar rather than fabricating either.
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

  const anyIndeterminate = entries.some((entry) => entry.indeterminate);

  return (
    <>
      <div className={styles.trayGrid}>
        {entries.map(
          ({ crop, pct, daysHeld, daysRemaining, readyOn, indeterminate }) => (
            <Link
              key={crop.id}
              to={`${basePath}/crops/${encodeURIComponent(crop.id)}`}
              className={styles.tray}
            >
              <span className={styles.trayGlyph}>
                <CropGlyph
                  ticker={crop.ticker}
                  sector={crop.sector}
                  stage={crop.stage}
                />
              </span>
              <span className={styles.trayTicker}>{crop.ticker}</span>
              <Meter
                pct={pct}
                tone="water"
                label={
                  indeterminate
                    ? `${crop.ticker}: not yet liftable, ${daysHeld} days held`
                    : `${crop.ticker}: ${daysHeld} days held, ${daysRemaining} to go`
                }
              />
              <span className={styles.trayDays}>
                {/* No known countdown (#7184): held days on their own, not a
                    "X / X" ratio that would read as a completed bar. */}
                {indeterminate
                  ? `${daysHeld} days held`
                  : `${daysHeld} / ${daysHeld + daysRemaining} days`}
              </span>
              <span className={styles.trayReady}>
                {indeterminate
                  ? 'Not yet liftable'
                  : readyOn
                    ? `Ready ${readyOn}`
                    : `${daysRemaining} days to go`}
              </span>
            </Link>
          )
        )}
      </div>
      <p className={styles.sectionNote}>
        {anyIndeterminate
          ? "Progress toward each holding's minimum holding period, where the backend knows it — some trays here are marked not sellable with no countdown to show."
          : "Progress toward each holding's minimum holding period, from the same rule the classic compliance screens use."}
      </p>
    </>
  );
}
