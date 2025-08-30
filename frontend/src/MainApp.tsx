import { useEffect, useState, lazy } from "react";
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
import { PerformanceDashboard } from "./components/PerformanceDashboard";

import { AlertsPanel } from "./components/AlertsPanel";
import { ComplianceWarnings } from "./components/ComplianceWarnings";
import useFetchWithRetry from "./hooks/useFetchWithRetry";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import Menu from "./components/Menu";
import { useRoute } from "./RouteContext";
import PriceRefreshControls from "./components/PriceRefreshControls";

const ScreenerQuery = lazy(() => import("./pages/ScreenerQuery"));
const TimeseriesEdit = lazy(() =>
  import("./pages/TimeseriesEdit").then((m) => ({ default: m.TimeseriesEdit })),
);
const Watchlist = lazy(() => import("./pages/Watchlist"));
const TopMovers = lazy(() => import("./pages/TopMovers"));
const DataAdmin = lazy(() => import("./pages/DataAdmin"));
const ScenarioTester = lazy(() => import("./pages/ScenarioTester"));
const SupportPage = lazy(() => import("./pages/Support"));

export default function MainApp() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { mode, setMode, selectedOwner, setSelectedOwner, selectedGroup, setSelectedGroup } = useRoute();

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [backendUnavailable, setBackendUnavailable] = useState(false);

  const ownersReq = useFetchWithRetry(getOwners);
  const groupsReq = useFetchWithRetry(getGroups);
  const unauthorized = ownersReq.unauthorized || groupsReq.unauthorized;

  useEffect(() => {
    if (ownersReq.data) setOwners(ownersReq.data);
  }, [ownersReq.data]);

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
  }, [mode, selectedOwner, selectedGroup, owners, groups, navigate, setSelectedOwner, setSelectedGroup]);

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

  if (unauthorized) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
        Unauthorized—check API token.
      </div>
    );
  }
  if (backendUnavailable) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
        Backend unavailable—retrying…
      </div>
    );
  }

  return (
    <>
      <LanguageSwitcher />
      <AlertsPanel />
      {mode !== "support" && (
        <Menu selectedOwner={selectedOwner} selectedGroup={selectedGroup} />
      )}

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
          <PerformanceDashboard owner={selectedOwner} />
        </>
      )}

      {mode === "transactions" && <TransactionsPage owners={owners} />}

      {mode === "screener" && <ScreenerQuery />}
      {mode === "timeseries" && <TimeseriesEdit />}
      {mode === "dataadmin" && <DataAdmin />}
      {mode === "watchlist" && <Watchlist />}
      {mode === "support" && <SupportPage />}
      {mode === "movers" && <TopMovers />}
      {mode === "scenario" && <ScenarioTester />}
    </>
  );
}

