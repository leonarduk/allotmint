import { useCallback, useEffect, useState, Suspense } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getGroupInstruments,
  getGroups,
  getOwners,
  getPortfolio,
  refreshPrices,
} from "./api";

import type {
  GroupSummary,
  InstrumentSummary,
  OwnerSummary,
  Portfolio,
} from "./types";

import { OwnerSelector } from "./components/OwnerSelector";
import { GroupSelector } from "./components/GroupSelector";
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
import DataAdmin from "./pages/DataAdmin";
import Support from "./pages/Support";
import ScenarioTester from "./pages/ScenarioTester";
import UserConfigPage from "./pages/UserConfig";
import BackendUnavailableCard from "./components/BackendUnavailableCard";
import ProfilePage from "./pages/Profile";
import Reports from "./pages/Reports";
import { orderedTabPlugins } from "./tabPlugins";
import { usePriceRefresh } from "./PriceRefreshContext";
import InstrumentSearchBar from "./components/InstrumentSearchBar";
import UserAvatar from "./components/UserAvatar";
import Logs from "./pages/Logs";
import AllocationCharts from "./pages/AllocationCharts";
import InstrumentAdmin from "./pages/InstrumentAdmin";
import Menu from "./components/Menu";
import Rebalance from "./pages/Rebalance";
import PensionForecast from "./pages/PensionForecast";
import TaxHarvest from "./pages/TaxHarvest";
import TaxAllowances from "./pages/TaxAllowances";
import RightRail from "./components/RightRail";
const PortfolioDashboard = lazyWithDelay(() => import("./pages/PortfolioDashboard"));

interface AppProps {
  onLogout?: () => void;
}

type Mode =
  | (typeof orderedTabPlugins)[number]["id"]
  | "profile"
  | "pension"
  | "market"
  | "rebalance";

// derive initial mode + id from path
const path = window.location.pathname.split("/").filter(Boolean);
const initialMode: Mode =
  path[0] === "member"
    ? "owner"
    : path[0] === "instrument"
    ? "instrument"
    : path[0] === "transactions"
    ? "transactions"
    : path[0] === "trading"
    ? "trading"
    : path[0] === "performance"
    ? "performance"
    : path[0] === "screener"
    ? "screener"
    : path[0] === "timeseries"
    ? "timeseries"
    : path[0] === "watchlist"
    ? "watchlist"
    : path[0] === "allocation"
    ? "allocation"
    : path[0] === "rebalance"
    ? "rebalance"
    : path[0] === "market"
    ? "market"
    : path[0] === "movers"
    ? "movers"
    : path[0] === "instrumentadmin"
    ? "instrumentadmin"
    : path[0] === "dataadmin"
    ? "dataadmin"
    : path[0] === "profile"
    ? "profile"
    : path[0] === "support"
    ? "support"
    : path[0] === "tax-harvest"
    ? "taxharvest"
    : path[0] === "tax-allowances"
    ? "taxallowances"
    : path[0] === "settings"
    ? "settings"
    : path[0] === "reports"
    ? "reports"
    : path[0] === "scenario"
    ? "scenario"
    : path[0] === "logs"
    ? "logs"
    : path[0] === "pension"
    ? "pension"
    : path.length === 0
    ? "group"
    : "movers";

const initialSlug = path[1] ?? "";

export default function App({ onLogout }: AppProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs } = useConfig();

  const params = new URLSearchParams(location.search);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedOwner, setSelectedOwner] = useState(
    initialMode === "owner" ? initialSlug : ""
  );
  const [selectedGroup, setSelectedGroup] = useState(
    initialMode === "instrument" ? initialSlug : params.get("group") ?? ""
  );

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(
    null
  );
  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  const { lastRefresh, setLastRefresh } = usePriceRefresh();
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const handleRetry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  const handleOwnerSelect = useCallback(
    (owner: string) => {
      setSelectedOwner(owner);
      navigate(`/performance/${owner}`);
    },
    [navigate],
  );

  const ownersReq = useFetchWithRetry(getOwners, 500, 5, [retryNonce]);
  const groupsReq = useFetchWithRetry(getGroups, 500, 5, [retryNonce]);

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    let newMode: Mode;
    switch (segs[0]) {
      case "member":
        newMode = "owner";
        break;
      case "profile":
        newMode = "profile";
        break;
      case "instrument":
        newMode = "instrument";
        break;
      case "transactions":
        newMode = "transactions";
        break;
      case "trading":
        newMode = "trading";
        break;
      case "performance":
        newMode = "performance";
        break;
      case "screener":
        newMode = "screener";
        break;
      case "timeseries":
        newMode = "timeseries";
        break;
      case "watchlist":
        newMode = "watchlist";
        break;
      case "allocation":
        newMode = "allocation";
        break;
      case "rebalance":
        newMode = "rebalance";
        break;
      case "market":
        newMode = "market";
        break;
      case "movers":
        newMode = "movers";
        break;
      case "instrumentadmin":
        newMode = "instrumentadmin";
        break;
      case "dataadmin":
        newMode = "dataadmin";
        break;
      case "support":
        newMode = "support";
        break;
      case "logs":
        newMode = "logs";
        break;
      case "pension":
        newMode = "pension";
        break;
      case "tax-harvest":
        newMode = "taxharvest";
        break;
      case "tax-allowances":
        newMode = "taxallowances";
        break;
      case "settings":
        newMode = "settings";
        break;
      case "reports":
        newMode = "reports";
        break;
      case "scenario":
        newMode = "scenario";
        break;
      default:
        newMode = segs.length === 0 ? "group" : "movers";
    }

    if (tabs[newMode] === false) {
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
    if (newMode === "owner") {
      setSelectedOwner(segs[1] ?? "");
    } else if (newMode === "instrument") {
      setSelectedGroup(segs[1] ?? "");
    } else if (newMode === "group") {
      setSelectedGroup(params.get("group") ?? "");
    }
  }, [location.pathname, location.search, tabs, navigate]);

  useEffect(() => {
    if (ownersReq.data) {
      setOwners(ownersReq.data);
      if (
        selectedOwner &&
        !ownersReq.data.some((o) => o.owner === selectedOwner)
      ) {
        setSelectedOwner("");
      }
    }
  }, [ownersReq.data, selectedOwner, setSelectedOwner]);

  useEffect(() => {
    if (groupsReq.data) setGroups(groupsReq.data);
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
    if (mode === "owner" && !selectedOwner && owners.length) {
      const owner = owners[0].owner;
      setSelectedOwner(owner);
      navigate(`/member/${owner}`, { replace: true });
    }
    if (mode === "instrument" && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      navigate(`/instrument/${slug}`, { replace: true });
    }
    if (mode === "group" && !selectedGroup && groups.length) {
      const slug = groups[0].slug;
      setSelectedGroup(slug);
      navigate(`/?group=${slug}`, { replace: true });
    }
  }, [mode, selectedOwner, selectedGroup, owners, groups, navigate]);

  // data fetching based on route
  useEffect(() => {
    if (mode === "owner" && selectedOwner) {
      setLoading(true);
      setErr(null);
      getPortfolio(selectedOwner)
        .then(setPortfolio)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedOwner]);

  useEffect(() => {
    if (mode === "instrument" && selectedGroup) {
      setLoading(true);
      setErr(null);
      getGroupInstruments(selectedGroup)
        .then(setInstruments)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [mode, selectedGroup]);

  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    setPriceRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());

      if (mode === "owner" && selectedOwner) {
        setPortfolio(await getPortfolio(selectedOwner));
      } else if (mode === "instrument" && selectedGroup) {
        setInstruments(await getGroupInstruments(selectedGroup));
      }
    } catch (e) {
      setPriceRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingPrices(false);
    }
  }

  if (backendUnavailable) {
    return <BackendUnavailableCard onRetry={handleRetry} />;
  }

  return (
    <div className="xl:flex xl:justify-center">
      <main style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <LanguageSwitcher />
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
      </div>
      <NotificationsDrawer
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
      />
      <div style={{ display: "flex", alignItems: "center", margin: "1rem 0" }}>
        <Menu
          selectedOwner={selectedOwner}
          selectedGroup={selectedGroup}
          onLogout={onLogout}
          style={{ flexGrow: 1, margin: 0 }}
        />
        <InstrumentSearchBar />
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
        <UserAvatar />
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? t("app.refreshing") : t("app.refreshPrices")}
        </button>
        {priceRefreshError && (
          <span
            style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}
          >
            {priceRefreshError}
          </span>
        )}
      </div>

      {/* OWNER VIEW */}
      {mode === "owner" && (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={handleOwnerSelect}
          />
          <ComplianceWarnings owners={selectedOwner ? [selectedOwner] : []} />
          <PortfolioView data={portfolio} loading={loading} error={err} />
        </>
      )}

      {/* GROUP VIEW */}
      {mode === "group" && groups.length > 0 && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={setSelectedGroup}
          />
          <ComplianceWarnings
            owners={groups.find((g) => g.slug === selectedGroup)?.members ?? []}
          />
          <GroupPortfolioView
            slug={selectedGroup}
            onSelectMember={(owner) => {
              setMode("owner");
              setSelectedOwner(owner);
              navigate(`/member/${owner}`);
            }}
          />
        </>
      )}

      {/* INSTRUMENT VIEW */}
      {mode === "instrument" && groups.length > 0 && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={setSelectedGroup}
          />
          {err && <p style={{ color: "red" }}>{err}</p>}
          {loading ? <p>{t("app.loading")}</p> : <InstrumentTable rows={instruments} />}
        </>
      )}

      {/* PERFORMANCE VIEW */}
      {mode === "performance" && (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={handleOwnerSelect}
          />
          <Suspense fallback={<PortfolioDashboardSkeleton />}>
            <PortfolioDashboard
              twr={null}
              irr={null}
              bestDay={null}
              worstDay={null}
              lastDay={null}
              alpha={null}
              trackingError={null}
              maxDrawdown={null}
              volatility={null}
              data={[]}
              owner={selectedOwner}
            />
          </Suspense>
        </>
      )}

      {mode === "transactions" && <TransactionsPage owners={owners} />}

      {mode === "trading" && <Trading />}

      {mode === "screener" && <ScreenerQuery />}
      {mode === "timeseries" && <TimeseriesEdit />}
      {mode === "instrumentadmin" && <InstrumentAdmin />}
      {mode === "dataadmin" && <DataAdmin />}
      {mode === "watchlist" && <Watchlist />}
      {mode === "allocation" && <AllocationCharts />}
      {mode === "rebalance" && <Rebalance />}
      {mode === "market" && <MarketOverview />}
      {mode === "movers" && <TopMovers />}
      {mode === "reports" && <Reports />}
      {mode === "taxharvest" && <TaxHarvest />}
      {mode === "taxallowances" && <TaxAllowances />}
      {mode === "support" && <Support />}
      {mode === "profile" && <ProfilePage />}
      {mode === "settings" && <UserConfigPage />}
      {mode === "logs" && <Logs />}
      {mode === "scenario" && <ScenarioTester />}
      {mode === "pension" && <PensionForecast />}
      </main>
      <Defer>
        <RightRail owner={selectedOwner} />
      </Defer>
    </div>
  );
}
