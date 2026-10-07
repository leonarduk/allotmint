import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Link, useParams } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  findCropByRouteId,
  formatGbp,
  formatPct,
  growthLevelFor,
  growthStageMeta,
  hasKnownHoldPeriodCountdown,
  isStillInPropagator,
  yieldLevelFor,
  type Crop,
} from '../plotModel';
import Meter from '../components/Meter';
import StarRating from '../components/StarRating';
import CropGlyph from '../components/CropGlyph';

/**
 * The first trait has two data paths (#7019), and the label always matches
 * the figure behind it:
 * - "Yield": the trailing 12-month income yield the backend derives from
 *   dividends/interest actually received, when there is any on record.
 * - "Growth": otherwise, the unrealised capital gain/loss. That is not an
 *   income yield and is never labelled as one.
 */
function harvestTraitFor(crop: Crop, t: TFunction) {
  if (crop.yieldPct !== null) {
    return {
      icon: '🧺',
      name: t('plot.crop.yield'),
      detail: t('plot.crop.yieldDetail', { pct: crop.yieldPct.toFixed(1) }),
      level: yieldLevelFor(crop.yieldPct),
      max: 5,
    };
  }
  return {
    icon: '🧺',
    name: t('plot.crop.growth'),
    // An unknown cost basis means an unknown gain, not £0 (#8471).
    detail:
      crop.gainGbp === null
        ? t('plot.crop.gainUnknown')
        : t('plot.crop.gainDetail', {
            gain: formatGbp(crop.gainGbp),
            pct: formatPct(crop.gainPct),
          }),
    level: growthLevelFor(crop.stage),
    max: 5,
  };
}

/**
 * The four "abilities" are just the holding's real stats given garden names,
 * with the underlying figure spelled out so nothing here is mystery-meat.
 */
function abilitiesFor(crop: Crop, t: TFunction) {
  return [
    harvestTraitFor(crop, t),
    {
      icon: '💚',
      name: t('plot.crop.vigour'),
      // A crop with no recorded intraday move is not "flat" — the backend
      // simply didn't send a day_change_gbp. Saying so explicitly keeps
      // "no data" distinct from a genuine 0.0% day (#vigour-constant).
      detail: !crop.hasMove
        ? t('plot.crop.noMoveToday')
        : `${t('plot.crop.pctToday', { pct: formatPct(crop.dayChangePct) })}${
            crop.stale
              ? ` · ${t('plot.crop.priceStale')}`
              : crop.freshness === 'unknown'
                ? ` · ${t('plot.crop.priceUnverified')}`
                : ''
          }`,
      level: Math.round(crop.vigour / 20),
      max: 5,
    },
    {
      icon: '🪴',
      name: t('plot.crop.rootDepth'),
      detail: t('plot.crop.rootDepthDetail', {
        pct: (crop.share * 100).toFixed(1),
      }),
      // Root depth reuses the 7-star plot-share rating, so it needs its own
      // scale rather than the 5 the other traits use.
      level: crop.stars,
      max: 7,
    },
    {
      icon: '⏳',
      name: t('plot.crop.hardiness'),
      detail:
        crop.daysHeld === null
          ? t('plot.crop.holdingAgeUnknown')
          : `${t('plot.crop.held', { count: crop.daysHeld })}${
              isStillInPropagator(crop)
                ? // A known countdown gets a specific date; `sell_eligible:
                  // false` on its own (#7184) — no positive
                  // `days_until_eligible` — only ever reads as "not yet
                  // liftable", never a stale or fabricated ready date.
                  hasKnownHoldPeriodCountdown(crop) &&
                  crop.nextEligibleSellDate
                  ? ` · ${t('plot.crop.inPropagatorUntil', {
                      date: crop.nextEligibleSellDate,
                    })}`
                  : ` · ${t('plot.crop.notYetLiftable')}`
                : crop.nextEligibleSellDate
                  ? ` · ${t('plot.crop.clearedPropagator', {
                      date: crop.nextEligibleSellDate,
                    })}`
                  : ` · ${t('plot.crop.readyToLift')}`
            }`,
      level: isStillInPropagator(crop) ? 2 : 5,
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
  const { t } = useTranslation();
  const { cropId = '' } = useParams();
  const { snapshot } = usePlotData();

  const decoded = safeDecode(cropId);
  const crop = findCropByRouteId(snapshot.crops, decoded);
  const index = crop ? snapshot.crops.indexOf(crop) : -1;

  if (!crop) {
    return (
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.crop.notFoundTitle')}</h2>
        <p className={styles.sectionNote}>
          {t('plot.crop.notFoundBody', { id: decoded })}{' '}
          <Link to={`${basePath}/crops`}>{t('plot.crop.backToRoster')}</Link>
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
          {crop.stale && <li className={styles.trait}>{t('plot.crop.stalePrice')}</li>}
          {crop.freshness === 'unknown' && (
            <li className={styles.trait}>{t('plot.crop.unverifiedPrice')}</li>
          )}
        </ul>
      </section>

      <div className={styles.detail} style={accentStyle}>
        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h3 className={styles.panelTitle}>{t('plot.crop.traits')}</h3>
          {abilitiesFor(crop, t).map((ability) => (
            <div key={ability.name} className={styles.abilityRow}>
              <span className={styles.abilityIcon} aria-hidden="true">
                {ability.icon}
              </span>
              <div>
                <div className={styles.abilityName}>
                  {ability.name}{' '}
                  <span className={styles.abilityLevel}>
                    {t('plot.crop.level', {
                      level: ability.level,
                      max: ability.max,
                    })}
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
          <div className={styles.radialLabel}>{t('plot.crop.plotValue')}</div>
          <div className={styles.radialValue}>{formatGbp(crop.valueGbp)}</div>
          <div className={(crop.gainPct ?? 0) >= 0 ? styles.gain : styles.loss}>
            {crop.gainGbp === null ? '—' : formatGbp(crop.gainGbp)} ({formatPct(crop.gainPct)})
          </div>
          <div style={{ width: '100%' }}>
            {crop.hasMove ? (
              <Meter
                pct={crop.vigour}
                label={t('plot.crop.vigourMeter', { value: crop.vigour })}
              />
            ) : (
              <p className={styles.sectionNote}>{t('plot.crop.noMoveToday')}</p>
            )}
          </div>
        </section>

        <section className={`${styles.panel} ${styles.panelGlow}`}>
          <h3 className={styles.panelTitle}>{t('plot.crop.ledger')}</h3>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>{t('plot.crop.units')}</span>
            <span className={styles.statValue}>{crop.units}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>{t('plot.crop.costBasis')}</span>
            <span className={styles.statValue}>{formatGbp(crop.costGbp)}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>{t('plot.crop.marketValue')}</span>
            <span className={styles.statValue}>{formatGbp(crop.valueGbp)}</span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>{t('plot.crop.today')}</span>
            <span
              className={`${styles.statValue} ${
                crop.dayChangePct >= 0 ? styles.gain : styles.loss
              }`}
            >
              {crop.hasMove ? formatPct(crop.dayChangePct) : t('plot.crop.noData')}
            </span>
          </div>
          <div className={styles.statRow}>
            <span className={styles.statLabel}>{t('plot.crop.lastPrice')}</span>
            <span className={styles.statValue}>
              {crop.lastPriceDate ?? t('plot.crop.unknown')}
            </span>
          </div>
          <p className={styles.sectionNote}>
            <Link to={`/instrument?ticker=${encodeURIComponent(crop.ticker)}`}>
              {t('plot.crop.openInstrument')}
            </Link>
          </p>
        </section>
      </div>

      <nav className={styles.toolbar} aria-label={t('plot.crop.neighbours')}>
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
          {t('plot.crop.allCrops')}
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
