import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  formatGbp,
  formatPct,
  germinatingCrops,
  growthStageMeta,
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
 * repeating the number already on screen.
 */
const RESOURCE_EXPLANATION: Record<string, string> = {
  water:
    'Water is how many trades you have left to make this month before the cap resets.',
  feed: "Feed is how much of this year's ISA/pension allowance headroom you still have to use.",
  sun: 'Sunlight is how much of your portfolio has a fresh price today — a stale price makes it droop.',
};

/**
 * Sunlight's copy above assumes every crop is confirmed either fresh or
 * stale. When some crops have no freshness signal at all (#7186), that
 * copy reads as "the empty part is stale", which is a claim we can't back
 * up — so it switches to language that names "unknown" as its own state.
 */
const SUNLIGHT_EXPLANATION_WITH_UNKNOWN =
  'Sunlight is how much of your portfolio has a *confirmed* fresh price today. A price with no freshness signal at all counts as unknown, not stale — it just has not been vouched for yet.';

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
}: {
  crop: Crop;
  role: string;
  rival?: boolean;
  basePath: string;
}) {
  const stage = growthStageMeta(crop.stage);
  const accentStyle = { '--plot-crop-accent': stage.accent } as CSSProperties;
  return (
    <Link
      to={`${basePath}/crops/${encodeURIComponent(crop.id)}`}
      className={styles.stageChampion}
      style={accentStyle}
      aria-label={`${role}: ${crop.ticker}, ${stage.label}, ${formatPct(crop.gainPct)}`}
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
      <span className={styles.stageMeta}>
        {role} · {stage.label} · {formatPct(crop.gainPct)}
      </span>
    </Link>
  );
}

/**
 * The hub screen: a glance-able read of the whole allotment — the standout
 * and struggling crops on the stage, the three resource meters, and the beds
 * (accounts) that make up the plot.
 */
export default function PlotHub({ basePath }: { basePath: string }) {
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

  const byGain = [...crops].sort((left, right) => right.gainPct - left.gainPct);
  const best = byGain[0];
  const worst = byGain.length > 1 ? byGain[byGain.length - 1] : undefined;
  const openChores = chores.filter((chore) => !chore.completed).length;
  const featured = crops.slice(0, 6);
  const germinating = germinatingCrops(crops);
  const streakDays = today ? buildStreakPath(dailyTotals, today) : [];
  const seasonGoals = buildSeasonGoals(snapshot, allowances, allowancesUnavailable);
  const seasonDone = seasonGoals.filter((goal) => goal.complete).length;
  const countdown = season ? seasonCountdown(season, new Date()) : null;

  return (
    <div className={styles.stack}>
      <section className={styles.stage} aria-label="Featured crops">
        {best ? (
          <>
            <Champion crop={best} role="Star grower" basePath={basePath} />
            <span className={styles.stageVersus} aria-hidden="true">
              VS
            </span>
            {worst ? (
              <Champion
                crop={worst}
                role="Needs attention"
                rival
                basePath={basePath}
              />
            ) : (
              <div />
            )}
          </>
        ) : (
          <p className={styles.stageEmpty}>
            Nothing planted yet — add a holding in the classic view and it will
            sprout here.
          </p>
        )}
      </section>

      {/* "How old is all this?" (#7186) — the SUNLIGHT meter can now say
          "unknown" instead of a false 100%, but that only tells the reader
          about individual holdings; the portfolio's own `as_of` date answers
          it for the whole plot without opening a crop. */}
      {snapshot.asOf && (
        <p className={styles.sectionNote}>Plot priced as of {snapshot.asOf}.</p>
      )}

      <section className={styles.pills} aria-label="Plot resources">
        {resources.map((resource) => {
          // SUNLIGHT with any unverified crops gets its own tip copy and a
          // visibly different bar treatment (#7186) — an empty/low bar must
          // not read as "confirmed stale", it reads as "unconfirmed".
          const sunIndeterminate = resource.id === 'sun' && sunUnknownCount > 0;
          const explanation = sunIndeterminate
            ? SUNLIGHT_EXPLANATION_WITH_UNKNOWN
            : RESOURCE_EXPLANATION[resource.id];
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
                      label={`What does ${resource.label} mean?`}
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
        <h2 className={styles.panelTitle}>Today&apos;s chores</h2>
        {choresAvailable ? (
          <div className={styles.choreRow}>
            <div className={styles.choreBody}>
              <div className={styles.choreTitle}>
                {openChores > 0
                  ? `${openChores} chore${openChores === 1 ? '' : 's'} still open`
                  : 'All chores done — the plot is tidy'}
              </div>
              <p className={styles.choreNote}>
                {snapshot.streak > 0
                  ? `${snapshot.streak}-day streak going. Keep it alive.`
                  : 'Finish a full day to start a streak.'}
              </p>
            </div>
            <Link className={styles.goButton} to={`${basePath}/chores`}>
              Go
            </Link>
          </div>
        ) : (
          <p className={styles.sectionNote}>
            Chore tracking is not enabled on this deployment.
          </p>
        )}
        {streakDays.length > 0 && (
          <StreakPath days={streakDays} streak={snapshot.streak} />
        )}
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {season ? `Growing season ${season.label}` : 'Growing season'} (
          {seasonDone}/{seasonGoals.length})
        </h2>
        {countdown && (
          <p className={styles.seasonCountdown}>{countdown.label}</p>
        )}
        <div className={styles.choreRow}>
          <div className={styles.choreBody}>
            <div className={styles.choreTitle}>
              {seasonDone} of {seasonGoals.length} season milestones reached
            </div>
            <p className={styles.choreNote}>
              Tiered goals across plot size, value, allowances, streak and rank.
            </p>
          </div>
          <Link className={styles.goButton} to={`${basePath}/season`}>
            View
          </Link>
        </div>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          Propagator ({germinating.length})
          <InfoTip
            label="What does Propagator mean?"
            to="/metrics-explained#propagator"
          >
            Crops still inside their minimum holding period, counting down to
            the date each one becomes eligible to sell.
          </InfoTip>
        </h2>
        <Propagator entries={germinating} basePath={basePath} />
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          Beds
          <InfoTip label="What does Beds mean?" to="/metrics-explained#beds">
            Each investment account is shown as a bed, with its holdings
            planted in it as crops.
          </InfoTip>
        </h2>
        {beds.length === 0 ? (
          <p className={styles.sectionNote}>
            No accounts found for this grower.
          </p>
        ) : (
          <div className={styles.seedGrid}>
            {beds.map((bed) => (
              <Link
                key={bed.id}
                to={`${basePath}/crops?bed=${encodeURIComponent(bed.id)}`}
                className={`${styles.seedCard} ${styles.seedCardLink}`}
                aria-label={`Show ${bed.name} crops`}
              >
                <span className={styles.seedTitle}>
                  <span aria-hidden="true">{bed.icon}</span> {bed.name}
                </span>
                <span className={styles.seedOwn}>
                  {bed.cropCount} crop{bed.cropCount === 1 ? '' : 's'}
                  {bed.owner ? ` · ${bed.owner}` : ''}
                  {/* #7186 — the bed's own last_updated can lag well behind
                      the portfolio as_of shown above; surfacing it here
                      means a stale bed doesn't hide behind a fresher
                      portfolio-wide date. */}
                  {bed.lastUpdated ? ` · priced ${bed.lastUpdated}` : ''}
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
        <h2 className={styles.panelTitle}>Biggest crops</h2>
        {featured.length === 0 ? (
          <p className={styles.sectionNote}>Nothing to show yet.</p>
        ) : (
          <>
            <div className={styles.cropGrid}>
              {featured.map((crop) => (
                <CropCard key={crop.id} crop={crop} basePath={basePath} />
              ))}
            </div>
            <p className={styles.sectionNote}>
              <Link to={`${basePath}/crops`}>See the full roster →</Link>
            </p>
          </>
        )}
      </section>
    </div>
  );
}
