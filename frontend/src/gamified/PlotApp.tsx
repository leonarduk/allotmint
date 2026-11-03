import type { ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Link, Route, Routes, useLocation, useSearchParams } from 'react-router-dom';
import type { OwnerSummary } from '../types';
import { getGroupDisplayName } from '../utils/groups';
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

function buildRailItems(t: TFunction): readonly RailItem[] {
  return [
    {
      to: PLOT_BASE_PATH,
      label: t('plot.rail.plot'),
      subtitle: t('plot.rail.plotSub'),
      end: true,
    },
    {
      to: `${PLOT_BASE_PATH}/crops`,
      label: t('plot.rail.crops'),
      subtitle: t('plot.rail.cropsSub'),
    },
    {
      to: `${PLOT_BASE_PATH}/chores`,
      label: t('plot.rail.chores'),
      subtitle: t('plot.rail.choresSub'),
    },
    {
      to: `${PLOT_BASE_PATH}/season`,
      label: t('plot.rail.season'),
      subtitle: t('plot.rail.seasonSub'),
    },
    {
      to: `${PLOT_BASE_PATH}/seeds`,
      label: t('plot.rail.seeds'),
      subtitle: t('plot.rail.seedsSub'),
    },
  ];
}

/**
 * Group options share the `<select>` with owner slugs, so they carry a prefix
 * that no owner slug can collide with (#7190).
 */
const GROUP_OPTION_PREFIX = 'group:';

function OwnerPicker() {
  const { t } = useTranslation();
  const { owners, pickerOwners, owner, groups, group } = usePlotData();
  const [searchParams, setSearchParams] = useSearchParams();

  // Writing `?owner=` / `?group=` here (rather than calling the context's
  // `setOwner` directly) makes the URL the single source of truth: PlotApp
  // already derives `requestedOwner`/`requestedGroup` from `location.search`
  // and feeds them into PlotDataProvider. That round trip is what makes a
  // grower change survive a refresh or a bookmark instead of only living in
  // local component state (#7192). `replace` (not the default push) so
  // cycling through growers doesn't spam the back button with one history
  // entry per selection. Only one of the two params is ever kept, so the URL
  // always names exactly one plot.
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const { value } = event.target;
    const next = new URLSearchParams(searchParams);
    if (value.startsWith(GROUP_OPTION_PREFIX)) {
      next.delete('owner');
      next.set('group', value.slice(GROUP_OPTION_PREFIX.length));
    } else {
      next.delete('group');
      next.set('owner', value);
    }
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

  // Same rule for a deep-linked `?group=` that `/groups` doesn't list (yet):
  // it keeps its own option so the select never shows a different plot's
  // name than the one on screen.
  const groupEntries =
    group && !groups.some((entry) => entry.slug === group)
      ? [{ slug: group, name: group, members: [] }, ...groups]
      : groups;

  // Hidden when there is nothing to switch between — one grower and no
  // group, which is how the picker has always behaved.
  if (optionEntries.length + groupEntries.length < 2) return null;
  return (
    <div className={styles.railFooter}>
      <label className={styles.railSubtitle} htmlFor="plot-owner">
        {t('plot.app.grower')}
      </label>
      <select
        id="plot-owner"
        className={styles.chipButton}
        value={group ? `${GROUP_OPTION_PREFIX}${group}` : owner}
        onChange={handleChange}
      >
        {groupEntries.length > 0 && (
          <optgroup label={t('plot.app.wholePlot')}>
            {groupEntries.map((entry) => (
              <option
                key={entry.slug}
                value={`${GROUP_OPTION_PREFIX}${entry.slug}`}
              >
                {getGroupDisplayName(entry.slug, entry.name, t)}
              </option>
            ))}
          </optgroup>
        )}
        {groupEntries.length > 0 ? (
          <optgroup label={t('plot.app.growers')}>
            {renderOwnerOptions(optionEntries)}
          </optgroup>
        ) : (
          renderOwnerOptions(optionEntries)
        )}
      </select>
    </div>
  );
}

function renderOwnerOptions(entries: readonly OwnerSummary[]) {
  return entries.map((entry) => (
    <option key={entry.owner} value={entry.owner}>
      {entry.full_name || entry.owner}
    </option>
  ));
}

/**
 * Shown for any `/plot/*` path that doesn't match a real screen. Previously
 * the catch-all route rendered the hub instead, so a mistyped or stale
 * bookmark silently "worked" with no indication the URL was wrong (#7192).
 * Mirrors CropDetail's "Crop not found" panel so both not-found states in
 * this skin look and behave the same way.
 */
function PlotNotFound({ basePath }: { basePath: string }) {
  const { t } = useTranslation();
  return (
    <section className={`${styles.panel} ${styles.panelGlow}`}>
      <h2 className={styles.panelTitle}>{t('plot.app.notFoundTitle')}</h2>
      <p className={styles.sectionNote}>
        {t('plot.app.notFoundBody')}{' '}
        <Link to={basePath}>{t('plot.app.backToPlot')}</Link>{' '}
        {t('plot.app.or')}{' '}
        <Link to={`${basePath}/crops`}>{t('plot.app.theRoster')}</Link>.
      </p>
    </section>
  );
}

function PlotShell() {
  const { t } = useTranslation();
  const { loading, error, snapshot, owner, group, refresh } = usePlotData();

  // Returning to the classic UI keeps the same grower (or group, which the
  // classic dashboard also reads from `?group=`) in scope so the two skins
  // stay in sync rather than dumping the user on a different plot.
  const classicPath = group
    ? `/?group=${encodeURIComponent(group)}`
    : owner
      ? `/?owner=${encodeURIComponent(owner)}`
      : '/';

  return (
    <div className={styles.plotRoot}>
      <HudBar snapshot={snapshot} classicPath={classicPath} />

      {error && (
        <div className={styles.errorBanner} role="alert">
          <p style={{ margin: 0 }}>{t('plot.app.loadError', { error })}</p>
          <button
            type="button"
            className={styles.chipButton}
            onClick={refresh}
            style={{ marginTop: '0.5rem' }}
          >
            {t('plot.app.tryAgain')}
          </button>
        </div>
      )}

      <div className={styles.layout}>
        <div>
          <PlotRail items={buildRailItems(t)} />
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
              {t('plot.app.loading')}
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
  const params = new URLSearchParams(location.search);
  const requestedOwner = params.get('owner');
  const requestedGroup = params.get('group');

  return (
    <PlotDataProvider
      requestedOwner={requestedOwner}
      requestedGroup={requestedGroup}
    >
      <PlotShell />
    </PlotDataProvider>
  );
}
