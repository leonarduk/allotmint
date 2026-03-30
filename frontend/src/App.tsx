import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  Suspense,
  type CSSProperties,
} from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getGroupInstruments,
  getGroups,
  getOwners,
  getPortfolio,
  listInstrumentMetadata,
} from "./api";

import type {
  GroupSummary,
  InstrumentMetadata,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
} from "./types";

import { OwnerSelector } from "./components/OwnerSelector";
import { PortfolioView } from "./components/PortfolioView";
import { GroupPortfolioView } from "./components/GroupPortfolioView";
import { InstrumentTable } from "./components/InstrumentTable";
import { TransactionsPage } from "./components/TransactionsPage";
import lazyWithDelay from "./utils/lazyWithDelay";
import PortfolioDashboardSkeleton from "./components/skeletons/PortfolioDashboardSkeleton";
import Defer from "./components/Defer";

import { NotificationsDrawer } from "./components/NotificationsDrawer";
import { ComplianceWarnings } from "./components/ComplianceWarnings";
import { ScreenerQuery } from "./pages/ScreenerQuery";
import useFetchWithRetry from "./hooks/useFetchWithRetry";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { TimeseriesEdit } from "./pages/TimeseriesEdit";
import Watchlist from "./pages/Watchlist";
import TopMovers from "./pages/TopMovers";
import MarketOverview from "./pages/MarketOverview";
import Trading from "./pages/Trading";
import { useConfig } from "./ConfigContext";
import { usePriceRefresh } from "./PriceRefreshContext";
import DataAdmin from "./pages/DataAdmin";
import Support from "./pages/Support";
import ScenarioTester from "./pages/ScenarioTester";
import UserConfigPage from "./pages/UserConfig";
import BackendUnavailableCard from "./components/BackendUnavailableCard";
import Reports from "./pages/Reports";
import ReportTemplateCreator from "./pages/ReportTemplateCreator";
import InstrumentSearchBarToggle from "./components/InstrumentSearchBar";
import UserAvatar from "./components/UserAvatar";
import AllocationCharts from "./pages/AllocationCharts";
import InstrumentAdmin from "./pages/InstrumentAdmin";
import Menu from "./components/Menu";
import Rebalance from "./pages/Rebalance";
import PensionForecast from "./pages/PensionForecast";
import TaxTools from "./pages/TaxTools";
import RightRail from "./components/RightRail";
import { sanitizeOwners } from "./utils/owners";
import {
  isDefaultGroupSlug,
  normaliseGroupSlug,
} from "./utils/groups";
import { deriveModeFromPathname } from "./pageManifest";
import { MAX_INSTRUMENT_CATALOGUE_ROWS } from "./constants/renderLimits";
const PerformanceDashboard = lazyWithDelay(
  () => import("./components/PerformanceDashboard"),
);
const InstrumentResearch = lazyWithDelay(
  () => import("./pages/InstrumentResearch"),
);
const VirtualPortfolio = lazyWithDelay(
  () => import("./pages/VirtualPortfolio"),
);

interface AppProps {
  onLogout?: () => void;
}

const path = window.location.pathname.split("/").filter(Boolean);
const initialMode = deriveModeFromPathname(window.location.pathname);
const initialSlug = path[1] ?? "";

function decodePathSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch (error) {
    console.warn("Failed to decode owner path segment; using raw value", {
      segment,
      error,
    });
    return segment;
  }
}

function encodePathSegment(segment: string): string {
  return encodeURIComponent(segment.trim());
}

type InstrumentMetadataWithSymbol = InstrumentMetadata & {
  symbol?: string | null;
};

const routeMarkerStyle: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  border: 0,
  opacity: 0,
  pointerEvents: "none",
  clip: "rect(0 0 0 0)",
  clipPath: "inset(50%)",
  overflow: "hidden",
};

function metadataToInstrumentSummary(metadata: InstrumentMetadata): InstrumentSummary {
  const metadataWithSymbol = metadata as InstrumentMetadataWithSymbol;
  const ticker = (() => {
    const rawTicker = typeof metadata.ticker === "string" ? metadata.ticker.trim() : "";
    if (rawTicker) {
      return rawTicker;
    }
    const symbol =
      typeof metadataWithSymbol.symbol === "string" && metadataWithSymbol.symbol.trim()
        ? metadataWithSymbol.symbol.trim()
        : "";
    if (!symbol) {
      return metadata.name?.trim() || "UNKNOWN";
    }
    const exchange =
      typeof metadata.exchange === "string" && metadata.exchange.trim()
        ? metadata.exchange.trim()
        : "";
    return exchange ? `${symbol}.${exchange}` : symbol;
  })();

  const exchange =
    typeof metadata.exchange === "string" && metadata.exchange.trim()
      ? metadata.exchange.trim()
      : null;
  const currency =
    typeof metadata.currency === "string" && metadata.currency.trim()
      ? metadata.currency.trim()
      : null;
  const grouping = (() => {
    const groupingCandidates = [
      metadata.grouping,
      metadata.sector,
      metadata.region,
      metadata.currency,
    ];
    for (const candidate of groupingCandidates) {
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate.trim();
      }
    }
    return null;
  })();
  const instrumentType = (() => {
    if (typeof metadata.instrument_type === "string" && metadata.instrument_type.trim()) {
      return metadata.instrument_type.trim();
    }
    if (typeof metadata.instrumentType === "string" && metadata.instrumentType.trim()) {
      return metadata.instrumentType.trim();
    }
    return null;
  })();

  const name = metadata.name?.trim() || ticker;

  return {
    ticker,
    name,
    grouping,
    exchange,
    currency,
    units: 0,
    market_value_gbp: 0,
    market_value_currency: currency,
    gain_gbp: 0,
    gain_currency: currency,
    gain_pct: 0,
    instrument_type: instrumentType,
  };
}

function sameOwnerList(left: OwnerSummary[], right: OwnerSummary[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((entry, index) => entry.owner === right[index]?.owner);
}

function sameGroupList(left: GroupSummary[], right: GroupSummary[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((entry, index) => entry.slug === right[index]?.slug);
}

export function getOwnerRootRedirectPath(
  pathname: string,
  selectedOwner: string,
  owners: OwnerSummary[],
): string | null {
  if (selectedOwner || owners.length === 0) return null;
  const segs = pathname.split("/").filter(Boolean);
  const atPortfolioRoot = segs[0] === "portfolio" && segs.length === 1;
  const atPerformanceRoot = segs[0] === "performance" && segs.length === 1;
  if (!atPortfolioRoot && !atPerformanceRoot) return null;
  const owner = owners[0].owner;
  const encodedOwner = encodePathSegment(owner);
  return atPerformanceRoot ? `/performance/${encodedOwner}` : `/portfolio/${encodedOwner}`;
}

export default function App({ onLogout }: AppProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const { lastRefresh } = usePriceRefresh();

  const params = new URLSearchParams(location.search);
  const isReportCreationRoute =
    location.pathname === "/reports/new" || location.pathname.startsWith("/reports/new/");
  const [mode, setMode] = useState(initialMode);
  const [selectedOwner, setSelectedOwner] = useState(
    initialMode === "owner" || initialMode === "performance"
      ? decodePathSegment(initialSlug)
      : "",
  );
  const [selectedGroup, setSelectedGroup] = useState(
    initialMode === "instrument"
      ? initialSlug
      : normaliseGroupSlug(params.get("group"))
  );

  const [researchTicker, setResearchTicker] = useState(
    initialMode === "research" ? decodeURIComponent(initialSlug) : ""
  );

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioAsOf, setPortfolioAsOf] = useState<string | null>(null);
  // Full catalogue stored in state — never truncated here.
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const portfolioCache = useRef(
    new Map<
      string,
      {
        data: Portfolio;
        fetchedAt: number;
        lastRefresh: string | null;
      }
    >(),
  );

  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const handleRetry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  const handleOwnerSelectPerformance = useCallback(
    (owner: string) => {
      const trimmedOwner = owner.trim();
      setSelectedOwner(trimmedOwner);
      navigate(`/performance/${encodePathSegment(trimmedOwner)}`);
    },
    [navigate],
  );

  const handleOwnerSelectPortfolio = useCallback(
    (owner: string) => {
      const trimmedOwner = owner.trim();
      setSelectedOwner(trimmedOwner);
      navigate(`/portfolio/${encodePathSegment(trimmedOwner)}`);
    },
    [navigate],
  );


  const handlePortfolioDateChange = useCallback((isoDate: string | null) => {
    setPortfolioAsOf(isoDate);
  }, []);

  const handleLogout = useCallback(() => {
    portfolioCache.current.clear();
    setPortfolio(null);
    onLogout?.();
  }, [onLogout]);

  const ownersReq = useFetchWithRetry(getOwners, 500, 5, [retryNonce]);
  const groupsReq = useFetchWithRetry(getGroups, 500, 5, [retryNonce]);

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    const newMode = deriveModeFromPathname(location.pathname);

    const isDisabled =
      tabs[newMode] === false || disabledTabs?.includes(newMode);
    if (isDisabled) {
      setMode("group");
      navigate("/", { replace: true });
      return;
    }
    if (newMode === "movers" && location.pathname !== "/movers") {
      setMode("movers");
      navigate("/movers", { replace: true });
      return;
    }
    setMode(newMode);
    if (newMode === "owner" || newMode === "performance") {
      if (segs[1]) {
        setSelectedOwner(decodePathSegment(segs[1]));
      }
    } else if (newMode === "instrument") {
      setSelectedGroup(segs[1] ?? "");
    } else if (newMode === "group") {
      const groupParam = params.get("group");
      setSelectedGroup(normaliseGroupSlug(groupParam));
      if (groupParam && isDefaultGroupSlug(groupParam) && location.search) {
        navigate("/", { replace: true });
      }
    } else if (newMode === "research") {
      setResearchTicker(segs[1] ? decodeURIComponent(segs[1] ?? "") : "");
    }
  }, [location.pathname, location.search, tabs, disabledTabs, navigate]);

  useEffect(() => {
    if (!ownersReq.data) return;
    const sanitizedOwners = sanitizeOwners(ownersReq.data);
    setOwners((currentOwners) =>
      sameOwnerList(currentOwners, sanitizedOwners) ? currentOwners : sanitizedOwners,
    );
  }, [ownersReq.data]);

  useEffect(() => {
    if (!selectedOwner) return;

    const match = owners.find(
      (o) => o.owner.toLowerCase() === selectedOwner.toLowerCase(),
    );

    if (match) {
      if (match.owner !== selectedOwner) {
        setSelectedOwner(match.owner);
      }
      return;
    }

    const segs = location.pathname.split("/").filter(Boolean);
    const routeSpecifiesOwner =
      (segs[0] === "portfolio" || segs[0] === "performance") && Boolean(segs[1]);

    if (!routeSpecifiesOwner) {
      setSelectedOwner("");
    }
  }, [owners, selectedOwner, setSelectedOwner, location.pathname]);

  useEffect(() => {
    if (groupsReq.data) {
      setGroups((currentGroups) =>
        sameGroupList(currentGroups, groupsReq.data ?? [])
          ? currentGroups
          : (groupsReq.data ?? []),
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
    const nextPath = getOwnerRootRedirectPath(location.pathname, selectedOwner, owners);
    if (nextPath) {
      navigate(nextPath, { replace: true });
    }
    if (mode === "instrument" && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      if (slug && slug !== "all") {
        navigate(`/instrument/${slug}`, { replace: true });
      }
    }
    if (mode === "group" && groups.length) {
      const hasSelection = groups.some((g) => g.slug === selectedGroup);
      if (!hasSelection) {
        const slug = groups[0].slug;
        setSelectedGroup(slug);
        if (isDefaultGroupSlug(slug)) {
          if (location.search) navigate("/", { replace: true });
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
  ]);

  // data fetching based on route
  useEffect(() => {

    if (mode === "owner" && selectedOwner) {
      const cacheKey = `${selectedOwner}::${portfolioAsOf ?? ""}::${lastRefresh ?? ""}`;
      const cached = portfolioCache.current.get(cacheKey);

      if (cached) {
        setPortfolio(cached.data);
        setErr(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      setErr(null);
      const request = portfolioAsOf
        ? getPortfolio(selectedOwner, { asOf: portfolioAsOf })
        : getPortfolio(selectedOwner);

      request
        .then((data) => {
          portfolioCache.current.set(cacheKey, {
            data,
            fetchedAt: Date.now(),
            lastRefresh,
          });
          setPortfolio(data);
        })
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedOwner, portfolioAsOf, lastRefresh]);

  useEffect(() => {
    if (mode === "owner" && selectedOwner) {
      setPortfolioAsOf(null);
    }
  }, [mode, selectedOwner]);

  useEffect(() => {
    if (mode === "instrument" && selectedGroup) {
      setLoading(true);
      setErr(null);
      // Store the full catalogue in state; render-time cap is applied below.
      const fetchPromise =
        selectedGroup === "all"
          ? listInstrumentMetadata().then((catalogue) =>
              catalogue.map((entry) => metadataToInstrumentSummary(entry)),
            )
          : getGroupInstruments(selectedGroup);
      fetchPromise
        .then(setInstruments)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedGroup]);

  // Render-only cap: never mutate the full instruments state.
  const visibleInstruments = useMemo(
    () => instruments.slice(0, MAX_INSTRUMENT_CATALOGUE_ROWS),
    [instruments],
  );

  const renderMainContent = () => {
    if (backendUnavailable) {
      return <BackendUnavailableCard onRetry={handleRetry} />;
    }

    return (
      <>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            margin: "1rem 0",
          }}
        >
          <LanguageSwitcher />
          <Menu
            selectedOwner={selectedOwner}
            selectedGroup={selectedGroup}
            onLogout={handleLogout}
            style={{ margin: 0 }}
          />
          <InstrumentSearchBarToggle />
          {mode === "owner" && (
            <OwnerSelector
              owners={owners}
              selected={selectedOwner}
              onSelect={handleOwnerSelectPortfolio}
            />
          )}
          {lastRefresh && (
            <span
              style={{
                background: "#eee",
                borderRadius: "1rem",
                padding: "0.25rem 0.5rem",
                fontSize: "0.75rem",
              }}
              title={t("app.last") ?? undefined}
            >
              {new Date(lastRefresh).toLocaleString()}
            </span>
          )}
          <button
            aria-label="notifications"
            onClick={() => setNotificationsOpen(true)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: "1.5rem",
            }}
          >
            🔔
          </button>
          <UserAvatar />
        </div>
        <NotificationsDrawer
          open={notificationsOpen}
          onClose={() => setNotificationsOpen(false)}
        />

        {/* OWNER VIEW */}
        {mode === "owner" && (
          <>
            <div data-testid="portfolio-owner-selector">
              <OwnerSelector
                owners={owners}
                selected={selectedOwner}
                onSelect={handleOwnerSelectPortfolio}
              />
            </div>
            <ComplianceWarnings owners={selectedOwner ? [selectedOwner] : []} />
            <PortfolioView
              data={portfolio}
              loading={loading}
              error={err}
              onDateChange={handlePortfolioDateChange}
            />
          </>
        )}

        {/* GROUP VIEW */}
        {mode === "group" && selectedGroup && (
          <>
            <ComplianceWarnings
              owners={groups.find((g) => g.slug === selectedGroup)?.members ?? []}
            />
            <GroupPortfolioView slug={selectedGroup} owners={owners} />
          </>
        )}

        {/* INSTRUMENT VIEW */}
        {mode === "instrument" && groups.length > 0 && (
          <>
            {err && <p style={{ color: "red" }}>{err}</p>}
            {loading ? (
              <p>{t("app.loading")}</p>
            ) : (
              <>
                <InstrumentTable rows={visibleInstruments} />
                {instruments.length > MAX_INSTRUMENT_CATALOGUE_ROWS && (
                  <p className="mt-2 text-xs text-slate-500">
                    {t("app.instrumentCatalogueTruncated", {
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
        {mode === "performance" && (
          <>
            <OwnerSelector
              owners={owners}
              selected={selectedOwner}
              onSelect={handleOwnerSelectPerformance}
            />
            <Suspense fallback={<PortfolioDashboardSkeleton />}>
              <PerformanceDashboard owner={selectedOwner} />
            </Suspense>
          </>
        )}

        {mode === "transactions" && <TransactionsPage owners={owners} />}

        {mode === "trading" && <Trading />}

        {mode === "screener" && <ScreenerQuery />}
        {mode === "timeseries" && <TimeseriesEdit />}
        {mode === "virtual" && (
          <Suspense fallback={<p>{t("app.loading")}</p>}>
            <VirtualPortfolio />
          </Suspense>
        )}
        {mode === "instrumentadmin" && <InstrumentAdmin />}
        {mode === "dataadmin" && <DataAdmin />}
        {mode === "watchlist" && <Watchlist />}
        {mode === "allocation" && <AllocationCharts />}
        {mode === "rebalance" && <Rebalance />}
        {mode === "market" && <MarketOverview />}
        {mode === "movers" && <TopMovers />}
        {mode === "reports" && (isReportCreationRoute ? <ReportTemplateCreator /> : <Reports />)}
        {mode === "taxtools" && <TaxTools />}
        {mode === "support" && <Support />}
        {mode === "settings" && <UserConfigPage />}
        {mode === "scenario" && <ScenarioTester />}
        {mode === "research" && (
          <Suspense fallback={<p>{t("app.loading")}</p>}>
            <InstrumentResearch ticker={researchTicker} />
          </Suspense>
        )}
        {mode === "pension" && <PensionForecast />}
      </>
    );
  };

  const rightRail = backendUnavailable ? null : (
    <Defer>
      <RightRail owner={selectedOwner} />
    </Defer>
  );

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
