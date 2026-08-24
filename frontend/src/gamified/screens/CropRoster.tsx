import { useMemo, useState } from 'react';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import { GROWTH_STAGES, type Crop } from '../plotModel';
import CropCard from '../components/CropCard';

type SortKey = 'value' | 'gain' | 'vigour' | 'name';

const SORTS: {
  id: SortKey;
  label: string;
  compare: (a: Crop, b: Crop) => number;
}[] = [
  {
    id: 'value',
    label: 'Plot share',
    compare: (a, b) => b.valueGbp - a.valueGbp,
  },
  { id: 'gain', label: 'Growth', compare: (a, b) => b.gainPct - a.gainPct },
  { id: 'vigour', label: 'Vigour', compare: (a, b) => b.vigour - a.vigour },
  {
    id: 'name',
    label: 'A–Z',
    compare: (a, b) => a.ticker.localeCompare(b.ticker),
  },
];

/** The collection screen: every holding as a crop tile, sortable and filterable. */
export default function CropRoster({ basePath }: { basePath: string }) {
  const { snapshot } = usePlotData();
  const [sort, setSort] = useState<SortKey>('value');
  const [bedFilter, setBedFilter] = useState<string>('all');

  const visible = useMemo(() => {
    const compare =
      SORTS.find((entry) => entry.id === sort)?.compare ?? SORTS[0].compare;
    return snapshot.crops
      .filter((crop) => bedFilter === 'all' || crop.bedId === bedFilter)
      .sort(compare);
  }, [snapshot.crops, sort, bedFilter]);

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const crop of snapshot.crops) {
      counts.set(crop.stage, (counts.get(crop.stage) ?? 0) + 1);
    }
    return counts;
  }, [snapshot.crops]);

  return (
    <div className={styles.stack}>
      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>Growth stages</h2>
        <ul className={styles.traitList}>
          {GROWTH_STAGES.map((stage) => (
            <li key={stage.id} className={styles.trait}>
              <span aria-hidden="true">{stage.icon}</span> {stage.label}:{' '}
              {stageCounts.get(stage.id) ?? 0}
            </li>
          ))}
        </ul>
        <p className={styles.sectionNote}>
          Stage comes from each holding&apos;s total gain, star rating from its
          share of plot value.
        </p>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          Crop roster ({visible.length}/{snapshot.crops.length})
        </h2>

        <div className={styles.toolbar} role="group" aria-label="Sort crops">
          {SORTS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-pressed={sort === entry.id}
              className={
                sort === entry.id
                  ? `${styles.chipButton} ${styles.chipButtonActive}`
                  : styles.chipButton
              }
              onClick={() => setSort(entry.id)}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className={styles.toolbar} role="group" aria-label="Filter by bed">
          <button
            type="button"
            aria-pressed={bedFilter === 'all'}
            className={
              bedFilter === 'all'
                ? `${styles.chipButton} ${styles.chipButtonActive}`
                : styles.chipButton
            }
            onClick={() => setBedFilter('all')}
          >
            All beds
          </button>
          {snapshot.beds.map((bed) => (
            <button
              key={bed.id}
              type="button"
              aria-pressed={bedFilter === bed.id}
              className={
                bedFilter === bed.id
                  ? `${styles.chipButton} ${styles.chipButtonActive}`
                  : styles.chipButton
              }
              onClick={() => setBedFilter(bed.id)}
            >
              <span aria-hidden="true">{bed.icon}</span> {bed.name}
            </button>
          ))}
        </div>

        {visible.length === 0 ? (
          <p className={styles.emptyState}>No crops in this bed yet.</p>
        ) : (
          <div className={styles.cropGrid}>
            {visible.map((crop) => (
              <CropCard key={crop.ticker} crop={crop} basePath={basePath} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
