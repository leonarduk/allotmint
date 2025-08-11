import { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getGroups, getOwners } from "./api";
import type { GroupSummary, OwnerSummary } from "./types";
import useFetchWithRetry from "./hooks/useFetchWithRetry";

import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { AlertsPanel } from "./components/AlertsPanel";
import { TransactionsPage } from "./components/TransactionsPage";
import { PerformanceDashboard } from "./components/PerformanceDashboard";
import { OwnerSelector } from "./components/OwnerSelector";
import { Screener } from "./pages/Screener";
import { QueryPage } from "./pages/QueryPage";
import { TimeseriesEdit } from "./pages/TimeseriesEdit";
import Dashboard from "./pages/Dashboard";

export default function App() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [backendUnavailable, setBackendUnavailable] = useState(false);

  const ownersReq = useFetchWithRetry(getOwners);
  const groupsReq = useFetchWithRetry(getGroups);

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

  if (backendUnavailable) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
        Backend unavailable—retrying…
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <LanguageSwitcher />
      <AlertsPanel />
      <Routes>
        <Route path="/" element={<Dashboard owners={owners} groups={groups} />} />
        <Route path="/member/:owner" element={<Dashboard owners={owners} groups={groups} />} />
        <Route path="/instrument/:group" element={<Dashboard owners={owners} groups={groups} />} />
        <Route path="/performance" element={<PerformanceRoute owners={owners} />} />
        <Route path="/transactions" element={<TransactionsPage owners={owners} />} />
        <Route path="/screener" element={<Screener />} />
        <Route path="/query" element={<QueryPage />} />
        <Route path="/timeseries" element={<TimeseriesEdit />} />
      </Routes>
      <p style={{ marginTop: "2rem", textAlign: "center" }}>
        <a href="/virtual">Virtual Portfolios</a>
        {" • "}
        <a href="/support">{t("app.supportLink")}</a>
      </p>
    </div>
  );
}

function PerformanceRoute({ owners }: { owners: OwnerSummary[] }) {
  const [selectedOwner, setSelectedOwner] = useState<string>("");

  useEffect(() => {
    if (!selectedOwner && owners.length) {
      setSelectedOwner(owners[0].owner);
    }
  }, [selectedOwner, owners]);

  return (
    <>
      <OwnerSelector
        owners={owners}
        selected={selectedOwner}
        onSelect={setSelectedOwner}
      />
      <PerformanceDashboard owner={selectedOwner} />
    </>
  );
}

