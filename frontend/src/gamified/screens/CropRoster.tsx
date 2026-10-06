import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import styles from '../plot.module.css';
import { usePlotData } from '../PlotDataContext';
import {
  GROWTH_STAGES,
  compareGainPctDesc,
  hasVigourSpread,
  type Crop,
} from '../plotModel';
import {
  loadFavourites,
  matchesSearch,
  saveFavourites,
  toggleFavourite,
} from '../favourites';
import CropCard from '../components/CropCard';
import CropGlyph from '../components/CropGlyph';
import InfoTip from '../../components/InfoTip';

type SortKey = 'value' | 'gain' | 'vigour' | 'name';

const SORTS: {
  id: SortKey;
  labelKey: string;
  compare: (a: Crop, b: Crop) => number;
}[] = [
  {
    id: 'value',
    labelKey: 'plot.roster.sortShare',
    compare: (a, b) => b.valueGbp - a.valueGbp,
  },
  { id: 'gain', labelKey: 'plot.roster.sortGrowth', compare: compareGainPctDesc },
  { id: 'vigour', labelKey: 'plot.roster.sortVigour', compare: (a, b) => b.vigour - a.vigour },
  {
    id: 'name',
    labelKey: 'plot.roster.sortAz',
    compare: (a, b) => a.ticker.localeCompare(b.ticker),
  },
];

/** The collection screen: every holding as a crop tile, searchable and sortable. */
export default function CropRoster({ basePath }: { basePath: string }) {
  const { t } = useTranslation();
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

  // The Vigour sort is only offered when at least two crops carry a real
  // intraday move — otherwise every crop scores the same 50/100 and the
  // button reorders nothing (#vigour-constant). If the user had selected
  // it and the data later loses its spread, fall back to Plot share.
  const vigourSortable = useMemo(
    () => hasVigourSpread(snapshot.crops),
    [snapshot.crops]
  );
  const availableSorts = useMemo(
    () => SORTS.filter((entry) => entry.id !== 'vigour' || vigourSortable),
    [vigourSortable]
  );
  const activeSort: SortKey =
    sort === 'vigour' && !vigourSortable ? 'value' : sort;

  const visible = useMemo(() => {
    const compare =
      SORTS.find((entry) => entry.id === activeSort)?.compare ??
      SORTS[0].compare;
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
  }, [
    snapshot.crops,
    activeSort,
    bedFilter,
    favouritesOnly,
    favourites,
    search,
  ]);

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
        <h2 className={styles.panelTitle}>
          {t('plot.roster.growthStages')}
          <InfoTip
            label={t('plot.roster.growthStagesLabel')}
            to="/metrics-explained#growth-stages"
          >
            {t('plot.roster.growthStagesTip')}
          </InfoTip>
        </h2>
        <ul className={styles.traitList}>
          {GROWTH_STAGES.map((stage) => (
            <li
              key={stage.id}
              className={`${styles.trait} ${styles.traitStage}`}
              style={{ '--plot-crop-accent': stage.accent } as CSSProperties}
            >
              <span className={styles.traitGlyph}>
                <CropGlyph species="pear" stage={stage.id} />
              </span>
              {stage.label}: {stageCounts.get(stage.id) ?? 0}
            </li>
          ))}
        </ul>
        <p className={styles.sectionNote}>
          {t('plot.roster.stageNote')}
        </p>
      </section>

      <section className={`${styles.panel} ${styles.panelGlow}`}>
        <h2 className={styles.panelTitle}>
          {t('plot.roster.title', {
            visible: visible.length,
            total: snapshot.crops.length,
          })}{' '}
          · {t('plot.roster.bedCount', { count: snapshot.beds.length })}
        </h2>

        <label className={styles.searchLabel} htmlFor="plot-crop-search">
          <span className={styles.srOnly}>{t('plot.roster.searchLabel')}</span>
          <input
            id="plot-crop-search"
            type="search"
            className={styles.searchInput}
            placeholder={t('plot.roster.searchPlaceholder')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <div className={styles.toolbar} role="group" aria-label={t('plot.roster.sortCrops')}>
          {availableSorts.map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-pressed={activeSort === entry.id}
              className={
                activeSort === entry.id
                  ? `${styles.chipButton} ${styles.chipButtonActive}`
                  : styles.chipButton
              }
              onClick={() => setSort(entry.id)}
            >
              {t(entry.labelKey)}
            </button>
          ))}
        </div>
        {!vigourSortable && snapshot.crops.length > 0 && (
          <p className={styles.sectionNote}>
            {t('plot.roster.vigourHidden')}
          </p>
        )}

        <div className={styles.toolbar} role="group" aria-label={t('plot.roster.filterCrops')}>
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
            {t('plot.roster.allBeds')}
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
            <span aria-hidden="true">★</span>{' '}
            {t('plot.roster.favourites', { count: favourites.size })}
          </button>
        </div>

        {visible.length === 0 ? (
          <p className={styles.emptyState}>{t('plot.roster.noMatch')}</p>
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
