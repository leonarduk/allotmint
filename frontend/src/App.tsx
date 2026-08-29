import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  Suspense,
  type CSSProperties,
} from 'react';
import { Navigate, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getGroupInstruments, getGroups, getOwners } from './api';

import type {
  GroupSummary,
  InstrumentSummary,
  OwnerSummary,
} from './types';

import { OwnerSelector } from './components/OwnerSelector';
import { PerformanceScopeSelector } from './components/PerformanceScopeSelector';
import type { PerformanceScope } from './components/PerformanceScopeSelector';
import { GroupPortfolioView } from './components/GroupPortfolioView';
import { InstrumentTable } from './components/InstrumentTable';
import { TransactionsPage } from './components/TransactionsPage';
import lazyWithDelay from './utils/lazyWithDelay';
import PortfolioDashboardSkeleton from './components/skeletons/PortfolioDashboardSkeleton';
import TableSkeleton from './components/skeletons/TableSkeleton';
import ChartSkeleton from './components/skeletons/ChartSkeleton';

import { ComplianceWarnings } from './components/ComplianceWarnings';
import { ScreenerQuery } from './pages/ScreenerQuery';
import useFetchWithRetry from './hooks/useFetchWithRetry';
import { TimeseriesEdit } from './pages/TimeseriesEdit';
import Watchlist from './pages/Watchlist';
import TopMovers from './pages/TopMovers';
import MarketOverview from './pages/MarketOverview';
import Trading from './pages/Trading';
import { useConfig } from './ConfigContext';
import { usePriceRefresh } from './PriceRefreshContext';
import DataAdmin from './pages/DataAdmin';
import Support from './pages/Support';
import ScenarioTester from './pages/ScenarioTester';
import UserConfigPage from './pages/UserConfig';
import BackendUnavailableCard from './components/BackendUnavailableCard';
import DisabledFeature from './components/DisabledFeature';
import Reports from './pages/Reports';
import ReportTemplateCreator from './pages/ReportTemplateCreator';
import AllocationCharts from './pages/AllocationCharts';
import InstrumentAdmin from './pages/InstrumentAdmin';
import AppHeader from './components/AppHeader';
import Rebalance from './pages/Rebalance';
import PensionForecast from './pages/PensionForecast';
import TaxTools from './pages/TaxTools';
import Alerts from './pages/Alerts';
import { sanitizeOwners, findOwnerForUser } from './utils/owners';
import { deriveModeFromLocation, readRouteScopeQuery } from './routes/registry';
import { useAuth } from './AuthContext';
import type { UserProfile } from './AuthContext';
import { isDefaultGroupSlug, normaliseGroupSlug } from './utils/groups';
import { deriveModeFromPathname } from './pageManifest';
import { MAX_INSTRUMENT_CATALOGUE_ROWS } from './constants/renderLimits';
import { decodePathSegment, encodePathSegment } from './utils/urlUtils';
import {
  downloadInstrumentsCsv,
  printInstrumentsPdf,
} from './lib/instrumentExports';
import { getFamilyMvpEntryPath } from './familyMvp';
import { completeTrackedChore } from './choreCompletion';

const PerformanceDashboard = lazyWithDelay(
  () => import('./components/PerformanceDashboard')
);
const InstrumentResearch = lazyWithDelay(
  () => import('./pages/InstrumentResearch')
);
const VirtualPortfolio = lazyWithDelay(
  () => import('./pages/VirtualPortfolio')
);

interface AppProps {
  onLogout?: () => void;
}

const routeMarkerStyle: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  border: 0,
  opacity: 0,
  pointerEvents: 'none',
  clip: 'rect(0 0 0 0)',
  clipPath: 'inset(50%)',
  overflow: 'hidden',
};

function sameOwnerList(left: OwnerSummary[], right: OwnerSummary[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((entry, index) => entry.owner === right[index]?.owner);
}

function sameGroupList(left: GroupSummary[], right: GroupSummary[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((entry, index) => entry.slug === right[index]?.slug);
}

// eslint-disable-next-line react-refresh/only-export-components
export function getOwnerRootRedirectPath(
  pathname: string,
  selectedOwner: string,
  owners: OwnerSummary[],
  user?: UserProfile | null,
  search = ''
): string | null {
  if (selectedOwner || owners.length === 0) return null;
  const segs = pathname.split('/').filter(Boolean);
  const atPortfolioRoot = segs[0] === 'portfolio' && segs.length === 1;
  const atPerformanceRoot = segs[0] === 'performance' && segs.length === 1;
  if (!atPortfolioRoot && !atPerformanceRoot) return null;
  // A bare `/performance?group=<slug>` is a deliberate group-scope landing
  // (#7228), not an unscoped root that should be forced onto an owner.
  if (atPerformanceRoot && readRouteScopeQuery(search).group) return null;
  const owner = findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
  const encodedOwner = encodePathSegment(owner);
  return atPerformanceRoot
    ? `/performance/${encodedOwner}`
    : `/portfolio/${encodedOwner}`;
}

// eslint-disable-next-line react-refresh/only-export-components
export function getFamilyMvpRedirectPath(
  pathname: string,
  search: string,
  familyMvpEnabled: boolean,
  entryPath: string | null = '/portfolio'
): string | null {
  if (!familyMvpEnabled) {
    return null;
  }
  // Family MVP redirect policy (#4641):
  // - Family MVP controls ONLY the default landing page. The single redirect we
  //   keep sends the bare root ('/' with no query) to the configured entry flow.
  // - Every other route is left untouched: enabled tabs (search, settings, …)
  //   must be fully navigable. Truly disabled tabs are handled separately by the
  //   tab gating in the route-sync effect, which shows an explanatory state.
  // - If every Family MVP tab is disabled, leave route selection to the caller.
  //
  // This is intentionally separate from getOwnerRootRedirectPath, which only
  // handles owner/performance root hydration once an owner list is available.
  if (!entryPath) {
    return null;
  }
  if (pathname === '/' && !search) {
    return entryPath;
  }
  return null;
}

export default function App({ onLogout }: AppProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs, familyMvpEnabled, configLoaded } = useConfig();
  const { lastRefresh } = usePriceRefresh();
  const { user } = useAuth();
  const familyMvpEntryPath = useMemo(
    () => (configLoaded ? getFamilyMvpEntryPath(tabs, disabledTabs) : null),
    [configLoaded, tabs, disabledTabs]
  );

  const scopeQuery = readRouteScopeQuery(location.search);
  const isReportCreationRoute =
    location.pathname === '/reports/new' ||
    location.pathname.startsWith('/reports/new/');
  const [mode, setMode] = useState(() =>
    deriveModeFromLocation(location.pathname, location.search)
  );
  const [selectedOwner, setSelectedOwner] = useState(() => {
    const initialPath = location.pathname.split('/').filter(Boolean);
    const initialMode = deriveModeFromLocation(location.pathname, location.search);
    return initialMode === 'owner' || initialMode === 'performance'
      ? initialPath[1]
        ? decodePathSegment(initialPath[1])
        : scopeQuery.owner ?? ''
      : initialMode === 'group'
        ? scopeQuery.owner ?? ''
        : '';
  });
  const [selectedGroup, setSelectedGroup] = useState(() => {
    const initialPath = location.pathname.split('/').filter(Boolean);
    return deriveModeFromPathname(location.pathname) === 'instrument'
      ? initialPath[1] ?? ''
      : normaliseGroupSlug(scopeQuery.group);
  });

  const [researchTicker, setResearchTicker] = useState(() => {
    const initialPath = location.pathname.split('/').filter(Boolean);
    return deriveModeFromPathname(location.pathname) === 'research'
      ? decodeURIComponent(initialPath[1] ?? '')
      : '';
  });

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  // Full catalogue stored in state — never truncated here.
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  const handleRetry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  const handleOwnerSelectPerformance = useCallback(
    (owner: string) => {
      const trimmedOwner = owner.trim();
      setSelectedOwner(trimmedOwner);
      setSelectedGroup('');
      navigate(`/performance/${encodePathSegment(trimmedOwner)}`);
    },
    [navigate]
  );

  const handleGroupSelectPerformance = useCallback(
    (slug: string) => {
      const trimmedSlug = slug.trim();
      setSelectedGroup(trimmedSlug);
      setSelectedOwner('');
      navigate(`/performance?group=${encodeURIComponent(trimmedSlug)}`);
    },
    [navigate]
  );

  const handleScopeSelectPerformance = useCallback(
    (scope: PerformanceScope) => {
      if (scope.kind === 'group') {
        handleGroupSelectPerformance(scope.slug);
      } else {
        handleOwnerSelectPerformance(scope.owner);
      }
    },
    [handleGroupSelectPerformance, handleOwnerSelectPerformance]
  );

  const handleOwnerSelectPortfolio = useCallback(
    (owner: string) => {
      const trimmedOwner = owner.trim();
      setSelectedOwner(trimmedOwner);
      navigate(`/?owner=${encodeURIComponent(trimmedOwner)}`);
    },
    [navigate]
  );

  const handleLogout = useCallback(() => {
    onLogout?.();
  }, [onLogout]);

  const ownersReq = useFetchWithRetry(getOwners, 500, 5, retryNonce);
  const groupsReq = useFetchWithRetry(getGroups, 500, 5, retryNonce);
  const selectedOwnerGroup = useMemo(
    () =>
      selectedOwner && groupsReq.data
        ? groupsReq.data.find((group) => group.slug === selectedOwner) ?? null
        : null,
    [groupsReq.data, selectedOwner]
  );
  const selectedGroupSummary = useMemo(
    () =>
      selectedGroup && groupsReq.data
        ? groupsReq.data.find((group) => group.slug === selectedGroup) ?? null
        : null,
    [groupsReq.data, selectedGroup]
  );
  // Redirect the bare root to the Family MVP entry path (the only Family MVP
  // redirect that remains — see getFamilyMvpRedirectPath, #4641). Fires on every
  // location change and whenever the config (and therefore familyMvpEnabled /
  // familyMvpEntryPath) resolves.
  useEffect(() => {
    const redirectPath = getFamilyMvpRedirectPath(
      location.pathname,
      location.search,
      familyMvpEnabled,
      familyMvpEntryPath
    );
    if (redirectPath) {
      navigate(redirectPath, { replace: true });
    }
  }, [familyMvpEnabled, familyMvpEntryPath, location.pathname, location.search, navigate]);

  // Sync route state (mode, selectedOwner, selectedGroup) with the current
  // location. Waits for config to load so that disabled-tab gating uses
  // the correct tab config. Also skips the sync when a Family MVP redirect
  // is about to fire, to avoid transient mode flips.
  useEffect(() => {
    if (!configLoaded) {
      return;
    }

    const redirectPath = getFamilyMvpRedirectPath(
      location.pathname,
      location.search,
      familyMvpEnabled,
      familyMvpEntryPath
    );
    if (redirectPath) {
      // The first useEffect will navigate; skip syncing mode for this location.
      return;
    }

    const segs = location.pathname.split('/').filter(Boolean);
    const scopeQuery = readRouteScopeQuery(location.search);
    const newMode = deriveModeFromLocation(location.pathname, location.search);

    const isDisabled =
      tabs[newMode] === false || disabledTabs?.includes(newMode);
    if (isDisabled) {
      setMode(newMode);
      return;
    }
    if (newMode === 'movers' && location.pathname !== '/movers') {
      setMode('movers');
      navigate('/movers', { replace: true });
      return;
    }
    setMode(newMode);
    if (newMode === 'owner' || newMode === 'performance') {
      const queryOwner = newMode === 'owner' ? scopeQuery.owner : null;
      // Performance also accepts a `?group=` scope (#7228), carried as a
      // query param rather than a path segment so it never collides with an
      // owner slug in /performance/:owner. It takes priority: a group query
      // param means the user deliberately chose the household view, so it
      // must not be clobbered by the owner auto-selection below.
      const queryGroup = newMode === 'performance' ? scopeQuery.group : null;
      if (queryGroup) {
        setSelectedGroup(normaliseGroupSlug(queryGroup));
        setSelectedOwner('');
      } else if (segs[1] || queryOwner) {
        if (newMode === 'performance') setSelectedGroup('');
        setSelectedOwner(
          segs[1] ? decodePathSegment(segs[1]) : queryOwner ?? ''
        );
      } else if (owners.length > 0) {
        if (newMode === 'performance') setSelectedGroup('');
        // URL redirect is handled by the render-time <Navigate> in renderMainContent.
        setSelectedOwner(findOwnerForUser(owners, user)?.owner ?? owners[0].owner);
      }
    } else if (newMode === 'instrument') {
      setSelectedGroup(segs[1] ?? '');
    } else if (newMode === 'group') {
      const groupParam = scopeQuery.group;
      setSelectedOwner(scopeQuery.owner ?? '');
      setSelectedGroup(normaliseGroupSlug(groupParam));
      // Skip this cleanup under Family MVP: stripping `?group=all` down to a
      // bare '/' would immediately re-trigger the entry-path redirect above
      // (bare '/' with no query is treated as "go to the MVP landing page"),
      // bouncing the group view straight back off (#5075).
      if (
        groupParam &&
        isDefaultGroupSlug(groupParam) &&
        location.search &&
        !familyMvpEnabled
      ) {
        navigate('/', { replace: true });
      }
    } else if (newMode === 'research') {
      setResearchTicker(segs[1] ? decodeURIComponent(segs[1] ?? '') : '');
    }
  }, [
    familyMvpEnabled,
    configLoaded,
    familyMvpEntryPath,
    location.pathname,
    location.search,
    tabs,
    disabledTabs,
    owners,
    navigate,
    user,
  ]);

  useEffect(() => {
    if (!ownersReq.data) return;
    const sanitizedOwners = sanitizeOwners(ownersReq.data);
    setOwners((currentOwners) =>
      sameOwnerList(currentOwners, sanitizedOwners)
        ? currentOwners
        : sanitizedOwners
    );
  }, [ownersReq.data]);

  useEffect(() => {
    if (!selectedOwner) return;

    const match = owners.find(
      (o) => o.owner.toLowerCase() === selectedOwner.toLowerCase()
    );

    if (match) {
      if (match.owner !== selectedOwner) {
        setSelectedOwner(match.owner);
      }
      return;
    }

    const segs = location.pathname.split('/').filter(Boolean);
    const scopeQuery = readRouteScopeQuery(location.search);
    const routeSpecifiesOwner =
      ((segs[0] === 'portfolio' || segs[0] === 'performance') &&
        Boolean(segs[1])) ||
      (segs.length === 0 && Boolean(scopeQuery.owner));

    if (!routeSpecifiesOwner) {
      setSelectedOwner('');
    }
  }, [owners, selectedOwner, setSelectedOwner, location.pathname, location.search]);

  useEffect(() => {
    if (groupsReq.data) {
      setGroups((currentGroups) =>
        sameGroupList(currentGroups, groupsReq.data ?? [])
          ? currentGroups
          : (groupsReq.data ?? [])
      );
    }
  }, [groupsReq.data]);

  useEffect(() => {
    if (ownersReq.error || groupsReq.error) {
      setBackendUnavailable(true);
    }
  }, [ownersReq.error, groupsReq.error]);

  useEffect(() => {
    if (ownersReq.data && groupsReq.data) {
      setBackendUnavailable(false);
    }
  }, [ownersReq.data, groupsReq.data]);

  // redirect to defaults if no selection provided
  useEffect(() => {
    const nextPath = getOwnerRootRedirectPath(
      location.pathname,
      selectedOwner,
      owners,
      user,
      location.search
    );
    if (nextPath) {
      navigate(nextPath, { replace: true });
    }
    if (mode === 'instrument' && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      if (slug && slug !== 'all') {
        navigate(`/instrument/${slug}`, { replace: true });
      }
    }
    if (mode === 'group' && groups.length) {
      const hasSelection = groups.some((g) => g.slug === selectedGroup);
      if (!hasSelection) {
        const slug = groups[0].slug;
        setSelectedGroup(slug);
        if (isDefaultGroupSlug(slug)) {
          if (location.search) navigate('/', { replace: true });
        } else {
          navigate(`/?group=${slug}`, { replace: true });
        }
      }
    }
  }, [
    mode,
    selectedOwner,
    selectedGroup,
    owners,
    groups,
    navigate,
    location.pathname,
    location.search,
    user,
  ]);

  // data fetching based on route
  useEffect(() => {
    if (mode === 'instrument' && selectedGroup) {
      setLoading(true);
      setErr(null);
      // Fetch live group holdings data for every group slug, including "all".
      const fetchPromise = getGroupInstruments(selectedGroup);
      fetchPromise
        .then(setInstruments)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedGroup]);

  // Render-only cap: never mutate the full instruments state.
  const visibleInstruments = useMemo(
    () => instruments.slice(0, MAX_INSTRUMENT_CATALOGUE_ROWS),
    [instruments]
  );
  const exportGroupLabel = selectedGroup || 'all';

  const portfolioGroupSlug =
    selectedOwnerGroup?.slug ?? (selectedGroup || '');

  // Completes the Plot chores screen's "Check overview" chore (#7003) the
  // first time the user actually lands on the classic overview after
  // clicking "Go" there — a no-op unless that navigation set the pending
  // marker, so visiting this page any other way does nothing.
  useEffect(() => {
    if ((mode === 'owner' || mode === 'group') && portfolioGroupSlug) {
      completeTrackedChore('check_overview');
    }
  }, [mode, portfolioGroupSlug]);
  // Each candidate source is memoized independently, keyed only on the
  // state that can actually change it. That keeps `portfolioComplianceOwners`
  // referentially stable across renders that touch unrelated state — e.g.
  // groupsReq resolving while an individual owner (not a group) is selected
  // still changes `selectedGroupSummary`'s identity, but that branch isn't
  // the one in use, so it must not force a new array here. ComplianceWarnings
  // keys a fetch effect on this array (via useFetch), and a fresh array
  // reference on every App re-render was firing /compliance/{owner} on every
  // re-render during hydration instead of once per owner (#6573).
  const ownerGroupComplianceMembers = useMemo(
    () => selectedOwnerGroup?.members ?? null,
    [selectedOwnerGroup]
  );
  const groupSummaryComplianceMembers = useMemo(
    () => selectedGroupSummary?.members ?? null,
    [selectedGroupSummary]
  );
  const singleSelectedOwnerCompliance = useMemo(
    () => (selectedOwner ? [selectedOwner] : null),
    [selectedOwner]
  );
  const emptyComplianceOwners = useMemo(() => [] as string[], []);
  const portfolioComplianceOwners =
    ownerGroupComplianceMembers ??
    singleSelectedOwnerCompliance ??
    groupSummaryComplianceMembers ??
    emptyComplianceOwners;

  const handleInstrumentExportCsv = useCallback(() => {
    downloadInstrumentsCsv(instruments, exportGroupLabel);
  }, [instruments, exportGroupLabel]);

  const handleInstrumentExportPdf = useCallback(() => {
    printInstrumentsPdf(instruments, exportGroupLabel);
  }, [instruments, exportGroupLabel]);

  const renderMainContent = () => {
    const isDisabled =
      configLoaded &&
      (tabs[mode] === false || disabledTabs?.includes(mode));
    if (isDisabled) {
      return <DisabledFeature />;
    }

    if (backendUnavailable) {
      return <BackendUnavailableCard onRetry={handleRetry} />;
    }

    // Synchronous render-time redirects for owner-root/performance-root paths.
    // Using <Navigate> instead of navigate()
    // from useEffect avoids deferred-update issues in data-router test environments.
    //
    const redirectSegs = location.pathname.split('/').filter(Boolean);
    const redirectMode = deriveModeFromPathname(location.pathname);
    const redirectScope = readRouteScopeQuery(location.search);
    // Derived straight from the current URL (not the shared `selectedGroup`
    // state, which defaults to "all" for unrelated modes like the merged
    // Dashboard) so a bare /performance or /performance/:owner never gets
    // misread as group scope before the location-sync effect below has run
    // (#7228).
    const performanceGroupSlug =
      redirectMode === 'performance' && redirectScope.group
        ? normaliseGroupSlug(redirectScope.group)
        : null;
    if (
      configLoaded &&
      redirectSegs[0] === 'portfolio' &&
      redirectSegs.length === 2
    ) {
      const params = new URLSearchParams(location.search);
      params.delete('group');
      params.set('owner', decodePathSegment(redirectSegs[1]));
      const search = params.toString();
      return <Navigate to={`/${search ? `?${search}` : ''}`} replace />;
    }
    if (
      configLoaded &&
      redirectMode === 'group' &&
      redirectScope.account &&
      !redirectScope.owner
    ) {
      return <Navigate to="/" replace />;
    }
    if (
      configLoaded &&
      !getFamilyMvpRedirectPath(location.pathname, location.search, familyMvpEnabled, familyMvpEntryPath) &&
      (redirectMode === 'owner' || redirectMode === 'performance') &&
      !redirectSegs[1] &&
      owners.length > 0 &&
      // A bare /performance?group=<slug> is a deliberate group-scope landing
      // (#7228) -- don't force it onto an owner.
      !(redirectMode === 'performance' && redirectScope.group)
    ) {
      const owner = findOwnerForUser(owners, user)?.owner ?? owners[0].owner;
      const destPath = redirectMode === 'performance'
        ? `/performance/${encodePathSegment(owner)}`
        : `/portfolio/${encodePathSegment(owner)}`;
      return <Navigate to={destPath} replace />;
    }

    return (
      <>
        <AppHeader
          selectedOwner={selectedOwner}
          selectedGroup={selectedGroup}
          onLogout={handleLogout}
          lastRefresh={lastRefresh}
        >
          {mode === 'owner' && (
            <div data-testid="portfolio-owner-selector">
              <OwnerSelector
                owners={owners}
                selected={selectedOwner}
                onSelect={handleOwnerSelectPortfolio}
              />
            </div>
          )}
        </AppHeader>

        {/* MERGED OWNER/GROUP PORTFOLIO VIEW */}
        {(mode === 'owner' || mode === 'group') && portfolioGroupSlug && (
          <>
            <ComplianceWarnings owners={portfolioComplianceOwners} />
            <GroupPortfolioView slug={portfolioGroupSlug} owners={owners} />
          </>
        )}

        {/* INSTRUMENT VIEW */}
        {mode === 'instrument' && groups.length > 0 && (
          <>
            <h1 className="mb-4 text-2xl">
              {t('app.modes.instrument', { defaultValue: 'Instruments' })}
            </h1>
            {selectedGroup === 'all' && instruments.length > 0 && (
              <div className="mb-4 rounded-lg border border-gray-800 bg-black/20 p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Export instruments
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={handleInstrumentExportCsv}
                    aria-label="Export instruments as CSV"
                    className="rounded border border-gray-700 px-3 py-1 text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                  >
                    Export CSV
                  </button>
                  <button
                    type="button"
                    onClick={handleInstrumentExportPdf}
                    aria-label="Export instruments as PDF"
                    className="rounded border border-gray-700 px-3 py-1 text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                  >
                    Export PDF
                  </button>
                </div>
              </div>
            )}
            {err && <p style={{ color: 'red' }}>{err}</p>}
            {loading ? (
              <TableSkeleton rows={8} columns={6} label={t('app.loading')} />
            ) : (
              <>
                <InstrumentTable rows={visibleInstruments} />
                {instruments.length > MAX_INSTRUMENT_CATALOGUE_ROWS && (
                  <p className="mt-2 text-xs text-slate-500">
                    {t('app.instrumentCatalogueTruncated', {
                      shown: MAX_INSTRUMENT_CATALOGUE_ROWS.toLocaleString(),
                      total: instruments.length.toLocaleString(),
                      defaultValue: `Showing first ${MAX_INSTRUMENT_CATALOGUE_ROWS.toLocaleString()} of ${instruments.length.toLocaleString()} instruments.`,
                    })}
                  </p>
                )}
              </>
            )}
          </>
        )}

        {/* PERFORMANCE VIEW */}
        {mode === 'performance' && (
          <>
            <PerformanceScopeSelector
              owners={owners}
              groups={groups}
              value={
                performanceGroupSlug
                  ? { kind: 'group', slug: performanceGroupSlug }
                  : selectedOwner
                    ? { kind: 'owner', owner: selectedOwner }
                    : null
              }
              onSelect={handleScopeSelectPerformance}
            />
            <Suspense fallback={<PortfolioDashboardSkeleton />}>
              <PerformanceDashboard
                owner={performanceGroupSlug ? null : selectedOwner}
                group={performanceGroupSlug}
              />
            </Suspense>
          </>
        )}

        {mode === 'transactions' && (
          <TransactionsPage
            owners={owners}
            inputOnly={location.pathname === '/input'}
          />
        )}

        {mode === 'trading' && <Trading />}

        {mode === 'screener' && <ScreenerQuery />}
        {mode === 'timeseries' && <TimeseriesEdit />}
        {mode === 'virtual' && (
          <Suspense fallback={<PortfolioDashboardSkeleton label={t('app.loading')} />}>
            <VirtualPortfolio owner={selectedOwner} />
          </Suspense>
        )}
        {mode === 'instrumentadmin' && <InstrumentAdmin />}
        {mode === 'dataadmin' && <DataAdmin />}
        {mode === 'watchlist' && <Watchlist />}
        {mode === 'allocation' && <AllocationCharts />}
        {mode === 'rebalance' && <Rebalance />}
        {mode === 'market' && <MarketOverview />}
        {mode === 'movers' && <TopMovers />}
        {mode === 'reports' &&
          (isReportCreationRoute ? <ReportTemplateCreator /> : <Reports />)}
        {mode === 'alerts' && <Alerts />}
        {mode === 'taxtools' && <TaxTools />}
        {mode === 'support' && <Support />}
        {mode === 'settings' && <UserConfigPage selectedOwner={selectedOwner} />}
        {mode === 'scenario' && <ScenarioTester />}
        {mode === 'research' && (
          <Suspense fallback={<ChartSkeleton height={400} label={t('app.loading')} />}>
            <InstrumentResearch ticker={researchTicker} />
          </Suspense>
        )}
        {mode === 'pension' && <PensionForecast />}
      </>
    );
  };

  const rightRail = null;

  return (
    <div className="mx-auto flex w-full max-w-screen-xl flex-col gap-4 px-4 py-4 xl:flex-row xl:items-start">
      <main className="min-w-0 flex-1">
        <div
          data-route-marker="active"
          data-testid="active-route-marker"
          data-mode={mode}
          data-pathname={location.pathname}
          style={routeMarkerStyle}
        />
        {renderMainContent()}
      </main>
      {rightRail}
    </div>
  );
}
