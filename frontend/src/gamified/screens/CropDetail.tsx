import type { CSSProperties } from 'react';
import { Link, useParams } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  findCropByRouteId,
  formatGbp,
  formatPct,
  growthLevelFor,
  growthStageMeta,
  type Crop,
} from '../plotModel';
import Meter from '../components/Meter';
import StarRating from '../components/StarRating';
import CropGlyph from '../components/CropGlyph';

/**
 * The four "abilities" are just the holding's real stats given garden names,
 * with the underlying figure spelled out so nothing here is mystery-meat.
 */
function abilitiesFor(crop: Crop) {
  return [
    {
      // Named "Growth", not "Yield": this is unrealised capital gain/loss,
      // not income/dividend yield, and the two are not interchangeable.
      // AllotMint doesn't yet surface a real dividend/income yield figure
      // per holding (see #7009), so this trait sticks to the number it can
      // honestly show rather than inventing a yield figure.
      icon: '🧺',
      name: 'Growth',
      detail: `${formatGbp(crop.gainGbp)} unrealised gain (${formatPct(crop.gainPct)})`,
      level: growthLevelFor(crop.stage),
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

/**
 * React Router hands path params through without decoding a malformed
 * sequence, so `decodeURIComponent('%zz')` throws URIError mid-render and
 * drops the screen into the error boundary. A crop id is user-controllable
 * via the URL bar, so fall back to the raw segment: it simply will not match
 * a crop, and the "not found" panel below is the right answer for it.
 */
function safeDecode(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/** The single-crop screen: portrait, traits, stats and neighbouring crops. */
export default function CropDetail({ basePath }: { basePath: string }) {
  const { cropId = '' } = useParams();
  const { snapshot } = usePlotData();

  const decoded = safeDecode(cropId);
  const crop = findCropByRouteId(snapshot.crops, decoded);
  const index = crop ? snapshot.crops.indexOf(crop) : -1;

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
          <span className={styles.detailGlyph}>
            <CropGlyph
              ticker={crop.ticker}
              sector={crop.sector}
              stage={crop.stage}
            />
          </span>
          <span className={styles.cropStageChip}>{stage.label}</span>
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
            to={`${basePath}/crops/${encodeURIComponent(previous.id)}`}
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
            to={`${basePath}/crops/${encodeURIComponent(next.id)}`}
          >
            {next.ticker} →
          </Link>
        )}
      </nav>
    </div>
  );
}
