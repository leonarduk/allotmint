import { Route, Routes, useLocation } from 'react-router-dom';
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
  const { owners, owner, setOwner } = usePlotData();
  if (owners.length < 2) return null;
  return (
    <div className={styles.railFooter}>
      <label className={styles.railSubtitle} htmlFor="plot-owner">
        Grower
      </label>
      <select
        id="plot-owner"
        className={styles.chipButton}
        value={owner}
        onChange={(event) => setOwner(event.target.value)}
      >
        {owners.map((entry) => (
          <option key={entry.owner} value={entry.owner}>
            {entry.full_name || entry.owner}
          </option>
        ))}
      </select>
    </div>
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
            <p className={styles.loading} role="status">
              Walking down to the allotment…
            </p>
          ) : (
            <Routes>
              <Route index element={<PlotHub basePath={PLOT_BASE_PATH} />} />
              <Route
                path="crops"
                element={<CropRoster basePath={PLOT_BASE_PATH} />}
              />
              <Route
                path="crops/:ticker"
                element={<CropDetail basePath={PLOT_BASE_PATH} />}
              />
              <Route path="chores" element={<ChoresScreen />} />
              <Route path="season" element={<SeasonTrack />} />
              <Route
                path="seeds"
                element={<SeedCatalogue basePath={PLOT_BASE_PATH} />}
              />
              <Route path="*" element={<PlotHub basePath={PLOT_BASE_PATH} />} />
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
