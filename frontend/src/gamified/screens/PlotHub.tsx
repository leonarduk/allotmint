import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { cropGlyph } from '../cropGlyph';
import { usePlotData } from '../PlotDataContext';
import { formatGbp, formatPct, growthStageMeta, type Crop } from '../plotModel';
import Meter, { type MeterTone } from '../components/Meter';
import CropCard from '../components/CropCard';

const RESOURCE_TONE: Record<string, MeterTone> = {
  water: 'water',
  feed: 'feed',
  sun: 'sun',
};

function Champion({
  crop,
  role,
  rival,
}: {
  crop: Crop;
  role: string;
  rival?: boolean;
}) {
  const stage = growthStageMeta(crop.stage);
  return (
    <div className={styles.stageChampion}>
      <span
        className={`${styles.stageGlyph} ${rival ? styles.stageGlyphRival : ''}`}
        aria-hidden="true"
      >
        {cropGlyph(crop.ticker, crop.sector)}
      </span>
      <span className={styles.stageName}>{crop.ticker}</span>
      <span className={styles.stageMeta}>
        {role} · {stage.label} · {formatPct(crop.gainPct)}
      </span>
    </div>
  );
}

/**
 * The hub screen: a glance-able read of the whole allotment — the standout
 * and struggling crops on the stage, the three resource meters, and the beds
 * (accounts) that make up the plot.
 */
export default function PlotHub({ basePath }: { basePath: string }) {
  const { snapshot, chores, choresAvailable } = usePlotData();
  const { crops, beds, resources } = snapshot;

  const byGain = [...crops].sort((left, right) => right.gainPct - left.gainPct);
  const best = byGain[0];
  const worst = byGain.length > 1 ? byGain[byGain.length - 1] : undefined;
  const openChores = chores.filter((chore) => !chore.completed).length;
  const featured = crops.slice(0, 6);

  return (
    <div className={styles.stack}>
      <section className={styles.stage} aria-label="Featured crops">
        {best ? (
          <>
            <Champion crop={best} role="Star grower" />
            <span className={styles.stageVersus} aria-hidden="true">
              VS
            </span>
            {worst ? (
              <Champion crop={worst} role="Needs attention" rival />
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

      <section className={styles.pills} aria-label="Plot resources">
        {resources.map((resource) => (
          <div key={resource.id} className={styles.pill}>
            <div className={styles.pillHead}>
              <span>
                <span aria-hidden="true">{resource.icon}</span> {resource.label}
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
        ))}
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
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Beds</h2>
        {beds.length === 0 ? (
          <p className={styles.sectionNote}>
            No accounts found for this grower.
          </p>
        ) : (
          <div className={styles.seedGrid}>
            {beds.map((bed) => (
              <div key={bed.id} className={styles.seedCard}>
                <span className={styles.seedTitle}>
                  <span aria-hidden="true">{bed.icon}</span> {bed.name}
                </span>
                <span className={styles.seedOwn}>
                  {bed.cropCount} crop{bed.cropCount === 1 ? '' : 's'}
                  {bed.owner ? ` · ${bed.owner}` : ''}
                </span>
                <span className={styles.cropValue}>
                  {formatGbp(bed.valueGbp)}
                </span>
              </div>
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
                <CropCard key={crop.ticker} crop={crop} basePath={basePath} />
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
