import type { CSSProperties } from 'react';
import { Link, useParams } from 'react-router-dom';
import styles from '../plot.module.css';
import { cropGlyph } from '../cropGlyph';
import { usePlotData } from '../PlotDataContext';
import { formatGbp, formatPct, growthStageMeta, type Crop } from '../plotModel';
import Meter from '../components/Meter';
import StarRating from '../components/StarRating';

/**
 * The four "abilities" are just the holding's real stats given garden names,
 * with the underlying figure spelled out so nothing here is mystery-meat.
 */
function abilitiesFor(crop: Crop) {
  return [
    {
      icon: '🧺',
      name: 'Yield',
      detail: `${formatGbp(crop.gainGbp)} unrealised gain (${formatPct(crop.gainPct)})`,
      level: crop.stage === 'wilting' ? 0 : growthLevel(crop),
      max: 5,
    },
    {
      icon: '💚',
      name: 'Vigour',
      detail: `${formatPct(crop.dayChangePct)} today${crop.stale ? ' · price data is stale' : ''}`,
      level: Math.round(crop.vigour / 20),
      max: 5,
    },
    {
      icon: '🪴',
      name: 'Root depth',
      detail: `${(crop.share * 100).toFixed(1)}% of total plot value`,
      // Root depth reuses the 7-star plot-share rating, so it needs its own
      // scale rather than the 5 the other traits use.
      level: crop.stars,
      max: 7,
    },
    {
      icon: '⏳',
      name: 'Hardiness',
      detail:
        crop.daysHeld === null
          ? 'Holding age unknown'
          : `Held ${crop.daysHeld} day${crop.daysHeld === 1 ? '' : 's'}${
              crop.sellEligible
                ? ' · ready to lift'
                : crop.nextEligibleSellDate
                  ? ` · in the propagator until ${crop.nextEligibleSellDate}`
                  : ' · not yet liftable'
            }`,
      level: crop.sellEligible ? 5 : 2,
      max: 5,
    },
  ];
}

function growthLevel(crop: Crop): number {
  // 0–5, mapped off total gain so the ability level tracks the stage chip.
  if (crop.gainPct >= 120) return 5;
  if (crop.gainPct >= 60) return 4;
  if (crop.gainPct >= 30) return 3;
  if (crop.gainPct >= 15) return 2;
  if (crop.gainPct > 0) return 1;
  return 0;
}

/** The single-crop screen: portrait, traits, stats and neighbouring crops. */
export default function CropDetail({ basePath }: { basePath: string }) {
  const { ticker = '' } = useParams();
  const { snapshot } = usePlotData();

  const decoded = decodeURIComponent(ticker);
  const index = snapshot.crops.findIndex((entry) => entry.ticker === decoded);
  const crop = index >= 0 ? snapshot.crops[index] : undefined;

  if (!crop) {
    return (
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Crop not found</h2>
        <p className={styles.sectionNote}>
          Nothing called “{decoded}” is growing in this plot.{' '}
          <Link to={`${basePath}/crops`}>Back to the roster</Link>
        </p>
      </section>
    );
  }

  const stage = growthStageMeta(crop.stage);
  const accentStyle = { '--plot-crop-accent': stage.accent } as CSSProperties;
  const previous = snapshot.crops[index - 1];
  const next = snapshot.crops[index + 1];

  return (
    <div className={styles.stack}>
      <section
        className={`${styles.panel} ${styles.panelGlow}`}
        style={accentStyle}
      >
        <h2 className={styles.panelTitle}>
          {crop.ticker} — {crop.name}
        </h2>
        <ul className={styles.traitList}>
          <li className={styles.trait}>{crop.bedName}</li>
          <li className={styles.trait}>{crop.sector}</li>
          <li className={styles.trait}>{crop.region}</li>
          <li className={styles.trait}>{crop.instrumentType}</li>
          {crop.stale && <li className={styles.trait}>Stale price</li>}
        </ul>
      </section>

      <div className={styles.detail} style={accentStyle}>
        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h3 className={styles.panelTitle}>Traits</h3>
          {abilitiesFor(crop).map((ability) => (
            <div key={ability.name} className={styles.abilityRow}>
              <span className={styles.abilityIcon} aria-hidden="true">
                {ability.icon}
              </span>
              <div>
                <div className={styles.abilityName}>
                  {ability.name}{' '}
                  <span className={styles.abilityLevel}>
                    {`Lv ${ability.level}/${ability.max}`}
                  </span>
                </div>
                <div className={styles.abilityLevel}>{ability.detail}</div>
              </div>
            </div>
          ))}
        </section>

        <section className={styles.detailPortrait}>
          <span className={styles.detailGlyph} aria-hidden="true">
            {cropGlyph(crop.ticker, crop.sector)}
          </span>
          <span className={styles.cropStageChip}>
            <span aria-hidden="true">{stage.icon}</span> {stage.label}
          </span>
          <StarRating value={crop.stars} />
          <div className={styles.radialLabel}>Plot value</div>
          <div className={styles.radialValue}>{formatGbp(crop.valueGbp)}</div>
          <div className={crop.gainPct >= 0 ? styles.gain : styles.loss}>
            {formatGbp(crop.gainGbp)} ({formatPct(crop.gainPct)})
          </div>
          <div style={{ width: '100%' }}>
            <Meter
              pct={crop.vigour}
              label={`Vigour ${crop.vigour} out of 100`}
            />
          </div>
        </section>

        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h3 className={styles.panelTitle}>Ledger</h3>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>Units</span>
            <span className={styles.statValue}>{crop.units}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>Cost basis</span>
            <span className={styles.statValue}>{formatGbp(crop.costGbp)}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>Market value</span>
            <span className={styles.statValue}>{formatGbp(crop.valueGbp)}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>Today</span>
            <span
              className={`${styles.statValue} ${
                crop.dayChangePct >= 0 ? styles.gain : styles.loss
              }`}
            >
              {formatPct(crop.dayChangePct)}
            </span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>Last price</span>
            <span className={styles.statValue}>
              {crop.lastPriceDate ?? 'unknown'}
            </span>
          </div>
          <p className={styles.sectionNote}>
            <Link to={`/instrument?ticker=${encodeURIComponent(crop.ticker)}`}>
              Open the full instrument view →
            </Link>
          </p>
        </section>
      </div>

      <nav className={styles.toolbar} aria-label="Neighbouring crops">
        {previous ? (
          <Link
            className={styles.chipButton}
            to={`${basePath}/crops/${encodeURIComponent(previous.ticker)}`}
          >
            ← {previous.ticker}
          </Link>
        ) : (
          <span />
        )}
        <Link className={styles.chipButton} to={`${basePath}/crops`}>
          All crops
        </Link>
        {next && (
          <Link
            className={styles.chipButton}
            to={`${basePath}/crops/${encodeURIComponent(next.ticker)}`}
          >
            {next.ticker} →
          </Link>
        )}
      </nav>
    </div>
  );
}
