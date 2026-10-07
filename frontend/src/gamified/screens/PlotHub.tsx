import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  attentionReasonFor,
  compareGainPctDesc,
  formatGbp,
  formatPct,
  germinatingCrops,
  growthStageMeta,
  neediestCrop,
  type Crop,
} from '../plotModel';
import {
  buildSeasonGoals,
  buildStreakPath,
  seasonCountdown,
} from '../seasonModel';
import Meter, { type MeterTone } from '../components/Meter';
import CropCard from '../components/CropCard';
import StreakPath from '../components/StreakPath';
import Propagator from '../components/Propagator';
import CropGlyph from '../components/CropGlyph';
import InfoTip from '../../components/InfoTip';

const RESOURCE_TONE: Record<string, MeterTone> = {
  water: 'water',
  feed: 'feed',
  sun: 'sun',
};

/**
 * One plain-English sentence per HUD meter, tying the garden metaphor back
 * to the real financial concept it stands for — see #7006. Kept separate
 * from `resource.hint` (the dynamic "3 of 7 trades left" caption that is
 * always visible) so the info tip explains the *concept* rather than
 * repeating the number already on screen. Values are i18n keys.
 */
const RESOURCE_EXPLANATION_KEY: Record<string, string> = {
  water: 'plot.hub.explainWater',
  feed: 'plot.hub.explainFeed',
  sun: 'plot.hub.explainSun',
};

/**
 * Sunlight's copy above assumes every crop is confirmed either fresh or
 * stale. When some crops have no freshness signal at all (#7186), that
 * copy reads as "the empty part is stale", which is a claim we can't back
 * up — so it switches to language that names "unknown" as its own state.
 */
const SUNLIGHT_EXPLANATION_WITH_UNKNOWN_KEY = 'plot.hub.explainSunUnknown';

// The glossary's Plot section (see #7230) uses "sunlight" as the anchor for
// the "sun" resource, matching its display label rather than its internal id.
const RESOURCE_GLOSSARY_ANCHOR: Record<string, string> = {
  water: 'water',
  feed: 'feed',
  sun: 'sunlight',
};

function Champion({
  crop,
  role,
  rival,
  basePath,
  reason,
}: {
  crop: Crop;
  role: string;
  rival?: boolean;
  basePath: string;
  /** When set, replaces the stage/gain meta with the actual problem. */
  reason?: string;
}) {
  const stage = growthStageMeta(crop.stage);
  const accentStyle = { '--plot-crop-accent': stage.accent } as CSSProperties;
  const meta = reason
    ? `${role} · ${reason}`
    : `${role} · ${stage.label} · ${formatPct(crop.gainPct)}`;
  return (
    <Link
      to={`${basePath}/crops/${encodeURIComponent(crop.id)}`}
      className={styles.stageChampion}
      style={accentStyle}
      aria-label={`${role}: ${crop.ticker}, ${reason ?? `${stage.label}, ${formatPct(crop.gainPct)}`}`}
    >
      <span
        className={`${styles.stageGlyph} ${rival ? styles.stageGlyphRival : ''}`}
        aria-hidden="true"
      >
        <CropGlyph
          ticker={crop.ticker}
          sector={crop.sector}
          stage={crop.stage}
        />
      </span>
      <span className={styles.stageName}>{crop.ticker}</span>
      <span className={styles.stageMeta}>{meta}</span>
    </Link>
  );
}

/**
 * The hub screen: a glance-able read of the whole allotment — the standout
 * and struggling crops on the stage, the resource meters, and the beds
 * (accounts) that make up the plot.
 */
export default function PlotHub({ basePath }: { basePath: string }) {
  const { t } = useTranslation();
  const {
    snapshot,
    chores,
    choresAvailable,
    allowances,
    allowancesUnavailable,
    season,
    dailyTotals,
    today,
  } = usePlotData();
  const { crops, beds, resources } = snapshot;
  const sunUnknownCount = crops.filter(
    (crop) => crop.freshness === 'unknown'
  ).length;

  const byGain = [...crops].sort(compareGainPctDesc);
  const best = byGain[0];
  // "Needs attention" is a judgement, not a ranking artefact: only a crop
  // with a real problem (compliance block, stale price, or an actual loss)
  // is nominated, and the card states which problem it is. A plot where
  // every holding is up shows a healthy-plot state instead of a scapegoat.
  const worst = neediestCrop(crops);
  const worstReason = worst ? attentionReasonFor(worst) : null;
  const openChores = chores.filter((chore) => !chore.completed).length;
  const featured = crops.slice(0, 6);
  const germinating = germinatingCrops(crops);
  const streakDays = today ? buildStreakPath(dailyTotals, today) : [];
  const seasonGoals = buildSeasonGoals(snapshot, allowances, allowancesUnavailable);
  const seasonDone = seasonGoals.filter((goal) => goal.complete).length;
  const countdown = season ? seasonCountdown(season, new Date()) : null;

  return (
    <div className={styles.stack}>
      <section className={styles.stage} aria-label={t('plot.hub.featuredCrops')}>
        {best ? (
          <>
            <Champion crop={best} role={t('plot.hub.starGrower')} basePath={basePath} />
            <span className={styles.stageVersus} aria-hidden="true">
              VS
            </span>
            {worst && worstReason ? (
              <Champion
                crop={worst}
                role={t('plot.hub.needsAttention')}
                reason={worstReason.label}
                rival
                basePath={basePath}
              />
            ) : (
              <p className={styles.stageEmpty}>
                {t('plot.hub.allHealthy')}
              </p>
            )}
          </>
        ) : (
          <p className={styles.stageEmpty}>
            {t('plot.hub.nothingPlanted')}
          </p>
        )}
      </section>

      {/* "How old is all this?" (#7186) — the SUNLIGHT meter can now say
          "unknown" instead of a false 100%, but that only tells the reader
          about individual holdings; the portfolio's own `as_of` date answers
          it for the whole plot without opening a crop. */}
      {snapshot.asOf && (
        <p className={styles.sectionNote}>
          {t('plot.hub.pricedAsOf', { date: snapshot.asOf })}
        </p>
      )}

      <section className={styles.pills} aria-label={t('plot.hub.resources')}>
        {resources.map((resource) => {
          // SUNLIGHT with any unverified crops gets its own tip copy and a
          // visibly different bar treatment (#7186) — an empty/low bar must
          // not read as "confirmed stale", it reads as "unconfirmed".
          const sunIndeterminate = resource.id === 'sun' && sunUnknownCount > 0;
          const explanation = sunIndeterminate
            ? t(SUNLIGHT_EXPLANATION_WITH_UNKNOWN_KEY)
            : t(RESOURCE_EXPLANATION_KEY[resource.id] ?? '', {
                defaultValue: '',
              });
          return (
            <div
              key={resource.id}
              className={
                sunIndeterminate
                  ? `${styles.pill} ${styles.pillIndeterminate}`
                  : styles.pill
              }
            >
              <div className={styles.pillHead}>
                <span>
                  <span aria-hidden="true">{resource.icon}</span>{' '}
                  {resource.label}
                  {explanation && (
                    <InfoTip
                      label={t('plot.hub.whatDoesMean', { term: resource.label })}
                      to={`/metrics-explained#${RESOURCE_GLOSSARY_ANCHOR[resource.id] ?? resource.id}`}
                    >
                      {explanation}
                    </InfoTip>
                  )}
                </span>
                <span className={styles.pillValue}>{resource.display}</span>
              </div>
              <Meter
                pct={resource.pct}
                tone={RESOURCE_TONE[resource.id] ?? 'growth'}
                label={`${resource.label}: ${resource.hint}`}
              />
              <p className={styles.pillHint}>{resource.hint}</p>
            </div>
          );
        })}
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.hub.todaysChores')}</h2>
        {choresAvailable ? (
          <div className={styles.choreRow}>
            <div className={styles.choreBody}>
              <div className={styles.choreTitle}>
                {openChores > 0
                  ? t('plot.hub.choresOpen', { count: openChores })
                  : t('plot.hub.choresAllDone')}
              </div>
              <p className={styles.choreNote}>
                {snapshot.streak > 0
                  ? t('plot.hub.streakGoing', { count: snapshot.streak })
                  : t('plot.hub.streakStart')}
              </p>
            </div>
            <Link className={styles.goButton} to={`${basePath}/chores`}>
              {t('plot.hub.go')}
            </Link>
          </div>
        ) : (
          <p className={styles.sectionNote}>
            {t('plot.hub.choresDisabled')}
          </p>
        )}
        {streakDays.length > 0 && (
          <StreakPath days={streakDays} streak={snapshot.streak} />
        )}
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {season
            ? t('plot.hub.growingSeasonLabel', { label: season.label })
            : t('plot.hub.growingSeason')}{' '}
          ({seasonDone}/{seasonGoals.length})
        </h2>
        {countdown && (
          <p className={styles.seasonCountdown}>{countdown.label}</p>
        )}
        <div className={styles.choreRow}>
          <div className={styles.choreBody}>
            <div className={styles.choreTitle}>
              {t('plot.hub.milestonesReached', {
                done: seasonDone,
                total: seasonGoals.length,
              })}
            </div>
            <p className={styles.choreNote}>
              {t('plot.hub.tieredGoals')}
            </p>
          </div>
          <Link className={styles.goButton} to={`${basePath}/season`}>
            {t('plot.hub.view')}
          </Link>
        </div>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {t('plot.hub.propagator')} ({germinating.length})
          <InfoTip
            label={t('plot.hub.whatDoesMean', {
              term: t('plot.hub.propagator'),
            })}
            to="/metrics-explained#propagator"
          >
            {t('plot.hub.propagatorTip')}
          </InfoTip>
        </h2>
        <Propagator entries={germinating} basePath={basePath} />
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {t('plot.hub.beds')}
          <InfoTip
            label={t('plot.hub.whatDoesMean', { term: t('plot.hub.beds') })}
            to="/metrics-explained#beds"
          >
            {t('plot.hub.bedsTip')}
          </InfoTip>
        </h2>
        {beds.length === 0 ? (
          <p className={styles.sectionNote}>
            {t('plot.hub.noAccounts')}
          </p>
        ) : (
          <div className={styles.seedGrid}>
            {beds.map((bed) => (
              <Link
                key={bed.id}
                to={`${basePath}/crops?bed=${encodeURIComponent(bed.id)}`}
                className={`${styles.seedCard} ${styles.seedCardLink}`}
                aria-label={t('plot.hub.showBedCrops', { name: bed.name })}
              >
                <span className={styles.seedTitle}>
                  <span aria-hidden="true">{bed.icon}</span> {bed.name}
                </span>
                <span className={styles.seedOwn}>
                  {t('plot.hub.cropCount', { count: bed.cropCount })}
                  {bed.owner ? ` · ${bed.owner}` : ''}
                  {/* #7186 — the bed's own last_updated can lag well behind
                      the portfolio as_of shown above; surfacing it here
                      means a stale bed doesn't hide behind a fresher
                      portfolio-wide date. */}
                  {bed.lastUpdated
                    ? ` · ${t('plot.hub.bedPriced', { date: bed.lastUpdated })}`
                    : ''}
                </span>
                <span className={styles.cropValue}>
                  {formatGbp(bed.valueGbp)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>{t('plot.hub.biggestCrops')}</h2>
        {featured.length === 0 ? (
          <p className={styles.sectionNote}>{t('plot.hub.nothingToShow')}</p>
        ) : (
          <>
            <div className={styles.cropGrid}>
              {featured.map((crop) => (
                <CropCard key={crop.id} crop={crop} basePath={basePath} />
              ))}
            </div>
            <p className={styles.sectionNote}>
              <Link to={`${basePath}/crops`}>{t('plot.hub.fullRoster')}</Link>
            </p>
          </>
        )}
      </section>
    </div>
  );
}
