import type { ChangeEvent } from 'react';
import { Link, Route, Routes, useLocation, useSearchParams } from 'react-router-dom';
import styles from './plot.module.css';
import HudBar from './components/HudBar';
import PlotRail, { type RailItem } from './components/PlotRail';
import { PlotDataProvider, usePlotData } from './PlotDataContext';
import PlotHub from './screens/PlotHub';
import CropRoster from './screens/CropRoster';
import CropDetail from './screens/CropDetail';
import ChoresScreen from './screens/ChoresScreen';
import SeasonTrack from './screens/SeasonTrack';
import SeedCatalogue from './screens/SeedCatalogue';

/** Mount point for the whole skin; kept in one place for links and tests. */
export const PLOT_BASE_PATH = '/plot';

const RAIL_ITEMS: readonly RailItem[] = [
  { to: PLOT_BASE_PATH, label: 'The Plot', subtitle: 'Overview', end: true },
  { to: `${PLOT_BASE_PATH}/crops`, label: 'Crops', subtitle: 'Your holdings' },
  { to: `${PLOT_BASE_PATH}/chores`, label: 'Chores', subtitle: 'Daily tasks' },
  {
    to: `${PLOT_BASE_PATH}/season`,
    label: 'Season',
    subtitle: 'Tax-year goals',
  },
  { to: `${PLOT_BASE_PATH}/seeds`, label: 'Seed shed', subtitle: 'Watchlist' },
];

function OwnerPicker() {
  const { owners, pickerOwners, owner } = usePlotData();
  const [searchParams, setSearchParams] = useSearchParams();

  // Writing `?owner=` here (rather than calling the context's `setOwner`
  // directly) makes the URL the single source of truth: PlotApp already
  // derives `requestedOwner` from `location.search` and feeds it into
  // PlotDataProvider, whose `requestedOwner` effect applies it to state. That
  // existing round trip is what makes a grower change survive a refresh or a
  // bookmark instead of only living in local component state (#7192).
  // `replace` (not the default push) so cycling through growers doesn't spam
  // the back button with one history entry per selection.
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const next = new URLSearchParams(searchParams);
    next.set('owner', event.target.value);
    setSearchParams(next, { replace: true });
  };

  // `<select value={owner}>` must always have a matching `<option>`, or the
  // browser silently falls back to selecting whichever option happens to be
  // first — e.g. `?owner=demo` would render demo's HUD and crops while the
  // dropdown reads the first grouped owner's name, and re-selecting that
  // same (already-selected-per-the-DOM) name fires no change event, so the
  // mismatch never recovers on its own. An owner reached via an explicit
  // deep link but excluded from `pickerOwners` (demo, currently) is
  // therefore added back as its own option — sourced from the full `owners`
  // list so it still gets a real display name — for as long as it stays
  // selected. Switching to any grouped grower drops it again (#7192).
  const activeOwnerOutsidePicker =
    owner && !pickerOwners.some((entry) => entry.owner === owner)
      ? (owners.find((entry) => entry.owner === owner) ?? {
          owner,
          full_name: owner,
          accounts: [],
        })
      : null;
  const optionEntries = activeOwnerOutsidePicker
    ? [activeOwnerOutsidePicker, ...pickerOwners]
    : pickerOwners;

  if (optionEntries.length < 2) return null;
  return (
    <div className={styles.railFooter}>
      <label className={styles.railSubtitle} htmlFor="plot-owner">
        Grower
      </label>
      <select
        id="plot-owner"
        className={styles.chipButton}
        value={owner}
        onChange={handleChange}
      >
        {optionEntries.map((entry) => (
          <option key={entry.owner} value={entry.owner}>
            {entry.full_name || entry.owner}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Shown for any `/plot/*` path that doesn't match a real screen. Previously
 * the catch-all route rendered the hub instead, so a mistyped or stale
 * bookmark silently "worked" with no indication the URL was wrong (#7192).
 * Mirrors CropDetail's "Crop not found" panel so both not-found states in
 * this skin look and behave the same way.
 */
function PlotNotFound({ basePath }: { basePath: string }) {
  return (
    <section className={`${styles.panel} ${styles.panelGlow}`}>
      <h2 className={styles.panelTitle}>Nothing growing here</h2>
      <p className={styles.sectionNote}>
        There's no plot screen at this path.{' '}
        <Link to={basePath}>Back to the plot</Link> or{' '}
        <Link to={`${basePath}/crops`}>the roster</Link>.
      </p>
    </section>
  );
}

function PlotShell() {
  const { loading, error, snapshot, owner, refresh } = usePlotData();

  // Returning to the classic UI keeps the same grower in scope so the two
  // skins stay in sync rather than dumping the user on a different owner.
  const classicPath = owner ? `/?owner=${encodeURIComponent(owner)}` : '/';

  return (
    <div className={styles.plotRoot}>
      <HudBar snapshot={snapshot} classicPath={classicPath} />

      {error && (
        <div className={styles.errorBanner} role="alert">
          <p style={{ margin: 0 }}>Could not load the plot: {error}</p>
          <button
            type="button"
            className={styles.chipButton}
            onClick={refresh}
            style={{ marginTop: '0.5rem' }}
          >
            Try again
          </button>
        </div>
      )}

      <div className={styles.layout}>
        <div>
          <PlotRail items={RAIL_ITEMS} />
          <OwnerPicker />
        </div>

        <main>
          {loading ? (
            // A plot-branded skeleton (same panel chrome every other screen
            // uses), not bare text — the HUD and rail above already render
            // with real data as soon as it's available, so only this panel
            // needs a placeholder while the grower's data is still in
            // flight (#7213).
            <section
              className={`${styles.panel} ${styles.panelGlow} ${styles.loading}`}
              role="status"
            >
              Walking down to the allotment…
            </section>
          ) : (
            <Routes>
              <Route index element={<PlotHub basePath={PLOT_BASE_PATH} />} />
              <Route
                path="crops"
                element={<CropRoster basePath={PLOT_BASE_PATH} />}
              />
              <Route
                path="crops/:cropId"
                element={<CropDetail basePath={PLOT_BASE_PATH} />}
              />
              <Route path="chores" element={<ChoresScreen />} />
              <Route path="season" element={<SeasonTrack />} />
              <Route
                path="seeds"
                element={<SeedCatalogue basePath={PLOT_BASE_PATH} />}
              />
              <Route
                path="*"
                element={<PlotNotFound basePath={PLOT_BASE_PATH} />}
              />
            </Routes>
          )}
        </main>
      </div>
    </div>
  );
}

/**
 * Plot mode: an optional arcade-style skin over the same portfolio, trail and
 * allowance data the classic UI renders. Mounted at /plot/* so the
 * conventional screens are completely untouched — the two are switchable, not
 * exclusive.
 */
export default function PlotApp() {
  const location = useLocation();
  const requestedOwner = new URLSearchParams(location.search).get('owner');

  return (
    <PlotDataProvider requestedOwner={requestedOwner}>
      <PlotShell />
    </PlotDataProvider>
  );
}
