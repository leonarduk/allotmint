import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import type { Crop, GerminatingCrop } from '../plotModel';
import Meter from './Meter';
import CropGlyph from './CropGlyph';

interface PropagatorProps {
  entries: readonly GerminatingCrop[];
  /** Crops past their hold period but awaiting approval (#10812). */
  awaitingApproval?: readonly Crop[];
  basePath: string;
}

interface AwaitingApprovalProps {
  crops: readonly Crop[];
  basePath: string;
}

/**
 * Crops that have served their hold period but still need approval to sell
 * (#10812), listed apart from the trays: their blocker is an approval the
 * user can request under Trading Rules, not time left to wait.
 */
function AwaitingApproval({ crops, basePath }: AwaitingApprovalProps) {
  const { t } = useTranslation();
  if (crops.length === 0) return null;
  const heading = t('plot.propagator.needsApprovalHeading', {
    count: crops.length,
  });
  return (
    <div role="group" aria-label={heading}>
      <p className={styles.sectionNote}>
        <strong>{heading}</strong> {t('plot.propagator.needsApprovalNote')}{' '}
        <Link to="/settings">{t('plot.propagator.tradingRulesLink')}</Link>
      </p>
      <div className={styles.trayGrid}>
        {crops.map((crop) => (
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
            {crop.daysHeld !== null && (
              <span className={styles.trayDays}>
                {t('plot.propagator.daysHeld', { daysHeld: crop.daysHeld })}
              </span>
            )}
            <span className={styles.trayReady}>
              {t('plot.propagator.needsApproval')}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

/**
 * Crops still serving their minimum holding period, shown as trays in a
 * propagator. Membership is `sell_eligible: false`, full stop (#7184).
 * Where the backend also gives a known, positive `days_until_eligible` /
 * `next_eligible_sell_date`, the tray shows real progress and a real ready
 * date; where it doesn't, `indeterminate` is true and the tray reads "not
 * yet liftable" with an empty bar rather than fabricating either.
 */
export default function Propagator({
  entries,
  awaitingApproval = [],
  basePath,
}: PropagatorProps) {
  const { t } = useTranslation();
  if (entries.length === 0) {
    return (
      <>
        <p className={styles.sectionNote}>{t('plot.propagator.empty')}</p>
        <AwaitingApproval crops={awaitingApproval} basePath={basePath} />
      </>
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
                    ? t('plot.propagator.meterIndeterminate', {
                        ticker: crop.ticker,
                        daysHeld,
                      })
                    : t('plot.propagator.meterProgress', {
                        ticker: crop.ticker,
                        daysHeld,
                        daysRemaining,
                      })
                }
              />
              <span className={styles.trayDays}>
                {/* No known countdown (#7184): held days on their own, not a
                    "X / X" ratio that would read as a completed bar. */}
                {indeterminate
                  ? t('plot.propagator.daysHeld', { daysHeld })
                  : t('plot.propagator.daysRatio', {
                      daysHeld,
                      total: daysHeld + daysRemaining,
                    })}
              </span>
              <span className={styles.trayReady}>
                {indeterminate
                  ? t('plot.propagator.notLiftable')
                  : readyOn
                    ? t('plot.propagator.readyOn', { date: readyOn })
                    : t('plot.propagator.daysToGo', { daysRemaining })}
              </span>
            </Link>
          )
        )}
      </div>
      <p className={styles.sectionNote}>
        {anyIndeterminate
          ? t('plot.propagator.noteIndeterminate')
          : t('plot.propagator.note')}
      </p>
      <AwaitingApproval crops={awaitingApproval} basePath={basePath} />
    </>
  );
}
