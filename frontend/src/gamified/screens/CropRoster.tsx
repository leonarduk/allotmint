import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import { GROWTH_STAGES, type Crop } from '../plotModel';
import {
  loadFavourites,
  matchesSearch,
  saveFavourites,
  toggleFavourite,
} from '../favourites';
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

/** The collection screen: every holding as a crop tile, searchable and sortable. */
export default function CropRoster({ basePath }: { basePath: string }) {
  const { snapshot, owner } = usePlotData();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sort, setSort] = useState<SortKey>('value');
  // The bed (account) filter is mirrored in the `bed` query param so other
  // screens — e.g. the hub's BEDS cards — can link straight into a
  // pre-filtered roster instead of re-implementing the filter logic.
  const [bedFilter, setBedFilterState] = useState<string>(
    () => searchParams.get('bed') ?? 'all'
  );
  const [search, setSearch] = useState('');
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const [favourites, setFavourites] = useState<Set<string>>(() => new Set());

  // Keep the filter in sync if the `bed` query param changes after mount
  // (e.g. navigating here again from the hub with a different account).
  useEffect(() => {
    const fromUrl = searchParams.get('bed') ?? 'all';
    setBedFilterState((current) => (current === fromUrl ? current : fromUrl));
  }, [searchParams]);

  const setBedFilter = useCallback(
    (bedId: string) => {
      setBedFilterState(bedId);
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (bedId === 'all') {
            next.delete('bed');
          } else {
            next.set('bed', bedId);
          }
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  // Favourites are namespaced per grower, so they reload when the owner
  // selector changes rather than leaking across portfolios.
  useEffect(() => {
    setFavourites(loadFavourites(owner));
  }, [owner]);

  const handleToggleFavourite = useCallback(
    (ticker: string) => {
      setFavourites((current) => {
        const next = toggleFavourite(current, ticker);
        saveFavourites(owner, next);
        return next;
      });
    },
    [owner]
  );

  const visible = useMemo(() => {
    const compare =
      SORTS.find((entry) => entry.id === sort)?.compare ?? SORTS[0].compare;
    return snapshot.crops
      .filter((crop) => bedFilter === 'all' || crop.bedId === bedFilter)
      .filter((crop) => !favouritesOnly || favourites.has(crop.ticker))
      .filter((crop) =>
        matchesSearch(
          [crop.ticker, crop.name, crop.bedName, crop.sector],
          search
        )
      )
      .sort(compare);
  }, [snapshot.crops, sort, bedFilter, favouritesOnly, favourites, search]);

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
          Crop roster ({visible.length}/{snapshot.crops.length}) ·{' '}
          {snapshot.beds.length} bed{snapshot.beds.length === 1 ? '' : 's'}
        </h2>

        <label className={styles.searchLabel} htmlFor="plot-crop-search">
          <span className={styles.srOnly}>Search crops</span>
          <input
            id="plot-crop-search"
            type="search"
            className={styles.searchInput}
            placeholder="Search ticker, name, bed or sector"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

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

        <div className={styles.toolbar} role="group" aria-label="Filter crops">
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
          <button
            type="button"
            aria-pressed={favouritesOnly}
            className={
              favouritesOnly
                ? `${styles.chipButton} ${styles.chipButtonActive}`
                : styles.chipButton
            }
            onClick={() => setFavouritesOnly((current) => !current)}
          >
            <span aria-hidden="true">★</span> Favourites ({favourites.size})
          </button>
        </div>

        {visible.length === 0 ? (
          <p className={styles.emptyState}>No crops match those filters.</p>
        ) : (
          <div className={styles.cropGrid}>
            {visible.map((crop) => (
              <CropCard
                key={crop.id}
                crop={crop}
                basePath={basePath}
                favourite={favourites.has(crop.ticker)}
                onToggleFavourite={handleToggleFavourite}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
