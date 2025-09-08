import { useCallback, useEffect, useState, lazy } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getGroupInstruments, getGroups, getOwners, getPortfolio } from "./api";
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
import PortfolioDashboard from "./pages/PortfolioDashboard";
import QuestBoard from "./components/QuestBoard";

import { NotificationsDrawer } from "./components/NotificationsDrawer";
import { ComplianceWarnings } from "./components/ComplianceWarnings";
import useFetchWithRetry from "./hooks/useFetchWithRetry";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import Menu from "./components/Menu";
import { useRoute } from "./RouteContext";
import PriceRefreshControls from "./components/PriceRefreshControls";
import { Header } from "./components/Header";
import InstallPwaPrompt from "./components/InstallPwaPrompt";
import BackendUnavailableCard from "./components/BackendUnavailableCard";

const ScreenerQuery = lazy(() => import("./pages/ScreenerQuery"));
const TimeseriesEdit = lazy(() =>
  import("./pages/TimeseriesEdit").then((m) => ({ default: m.TimeseriesEdit })),
);
const Watchlist = lazy(() => import("./pages/Watchlist"));
const TopMovers = lazy(() => import("./pages/TopMovers"));
const DataAdmin = lazy(() => import("./pages/DataAdmin"));
const InstrumentAdmin = lazy(() => import("./pages/InstrumentAdmin"));
const ScenarioTester = lazy(() => import("./pages/ScenarioTester"));
const SupportPage = lazy(() => import("./pages/Support"));
const LogsPage = lazy(() => import("./pages/Logs"));

export default function MainApp() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { mode, setMode, selectedOwner, setSelectedOwner, selectedGroup, setSelectedGroup } = useRoute();

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);
  const [tradeInfo, setTradeInfo] = useState<{ tradesThisMonth: number; tradesRemaining: number } | null>(null);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  const ownersReq = useFetchWithRetry(getOwners, 500, 5, [retryNonce]);
  const groupsReq = useFetchWithRetry(getGroups, 500, 5, [retryNonce]);
  const demoOnly =
    ownersReq.data?.length === 1 && ownersReq.data[0].owner === "demo";
  const unauthorized = demoOnly
    ? ownersReq.unauthorized
    : ownersReq.unauthorized || groupsReq.unauthorized;

  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const handleRetry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

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
    if (ownersReq.error || (!demoOnly && groupsReq.error)) {
      setBackendUnavailable(true);
    }
  }, [ownersReq.error, groupsReq.error, demoOnly]);

  useEffect(() => {
    if (ownersReq.data && (demoOnly || groupsReq.data)) {
      setBackendUnavailable(false);
    }
  }, [ownersReq.data, groupsReq.data, demoOnly]);

  // when only the demo owner is available, ensure we show the owner view
  useEffect(() => {
    if (demoOnly) {
      setMode("owner");
    }
  }, [demoOnly, setMode]);

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
  }, [mode, selectedOwner, selectedGroup, owners, groups, navigate, setSelectedOwner, setSelectedGroup]);

  // data fetching based on route
  useEffect(() => {
    if (mode === "owner" && selectedOwner) {
      setLoading(true);
      setErr(null);
      getPortfolio(selectedOwner)
        .then((p) => {
          setPortfolio(p);
          setTradeInfo({
            tradesThisMonth: p.trades_this_month,
            tradesRemaining: p.trades_remaining,
          });
        })
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

  if (unauthorized) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
        Unauthorized—check API token.
      </div>
    );
  }
  if (backendUnavailable) {
    return (
      <BackendUnavailableCard
        onRetry={handleRetry}
      />
    );
  }

  return (
    <>
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
      <InstallPwaPrompt />
      <NotificationsDrawer
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
      />
      <Menu selectedOwner={selectedOwner} selectedGroup={selectedGroup} />

      <Header
        tradesThisMonth={tradeInfo?.tradesThisMonth}
        tradesRemaining={tradeInfo?.tradesRemaining}
      />

      <QuestBoard />

      <PriceRefreshControls
        mode={mode}
        selectedOwner={selectedOwner}
        selectedGroup={selectedGroup}
        onPortfolio={setPortfolio}
        onInstruments={setInstruments}
      />

      {/* OWNER VIEW */}
      {mode === "owner" && (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={setSelectedOwner}
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
            owners={
              groups.find((g) => g.slug === selectedGroup)?.members ?? []
            }
          />
          <GroupPortfolioView
            slug={selectedGroup}
            onSelectMember={(owner) => {
              setMode("owner");
              setSelectedOwner(owner);
              navigate(`/member/${owner}`);
            }}
            onTradeInfo={(info) =>
              setTradeInfo(
                info
                  ? {
                      tradesThisMonth: info.trades_this_month ?? 0,
                      tradesRemaining: info.trades_remaining ?? 0,
                    }
                  : null,
              )
            }
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
            onSelect={setSelectedOwner}
          />
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
        </>
      )}

      {mode === "transactions" && <TransactionsPage owners={owners} />}

      {mode === "screener" && <ScreenerQuery />}
      {mode === "timeseries" && <TimeseriesEdit />}
      {mode === "instrumentadmin" && <InstrumentAdmin />}
      {mode === "dataadmin" && <DataAdmin />}
      {mode === "watchlist" && <Watchlist />}
      {mode === "support" && <SupportPage />}
      {mode === "movers" && <TopMovers />}
      {mode === "logs" && <LogsPage />}
      {mode === "scenario" && <ScenarioTester />}
    </>
  );
}

