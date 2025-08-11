import { useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getGroups,
  getOwners,
} from "./api";
import type { GroupSummary, OwnerSummary } from "./types";
import useFetchWithRetry from "./hooks/useFetchWithRetry";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { AlertsPanel } from "./components/AlertsPanel";
import { NavigationBar } from "./components/NavigationBar";
import GroupPage from "./pages/GroupPage";
import InstrumentPage from "./pages/InstrumentPage";
import OwnerPage from "./pages/OwnerPage";
import PerformancePage from "./pages/PerformancePage";
import { TransactionsPage } from "./components/TransactionsPage";
import { Screener } from "./pages/Screener";
import { QueryPage } from "./pages/QueryPage";
import { TimeseriesEdit } from "./pages/TimeseriesEdit";
import { TradingAgent } from "./pages/TradingAgent";

export default function App() {
  const { t } = useTranslation();
  const [relativeView, setRelativeView] = useState(true);

  const ownersReq = useFetchWithRetry<OwnerSummary[]>(getOwners);
  const groupsReq = useFetchWithRetry<GroupSummary[]>(getGroups);

  if (ownersReq.error || groupsReq.error) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
        Backend unavailable—retrying…
      </div>
    );
  }

  const owners = ownersReq.data ?? [];
  const groups = groupsReq.data ?? [];

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <LanguageSwitcher />
      <AlertsPanel />
      <NavigationBar />
      <div style={{ marginBottom: "1rem" }}>
        <label>
          <input
            type="checkbox"
            checked={relativeView}
            onChange={(e) => setRelativeView(e.target.checked)}
          />{" "}
          {t("app.relativeView")}
        </label>
      </div>
      <Routes>
        <Route
          path="group"
          element={
            <div role="tabpanel" id="tabpanel-group" aria-labelledby="tab-group">
              <GroupPage groups={groups} relativeView={relativeView} />
            </div>
          }
        />
        <Route
          path="instrument"
          element={
            <div
              role="tabpanel"
              id="tabpanel-instrument"
              aria-labelledby="tab-instrument"
            >
              <InstrumentPage groups={groups} />
            </div>
          }
        />
        <Route
          path="owner"
          element={
            <div role="tabpanel" id="tabpanel-owner" aria-labelledby="tab-owner">
              <OwnerPage owners={owners} relativeView={relativeView} />
            </div>
          }
        />
        <Route
          path="performance"
          element={
            <div
              role="tabpanel"
              id="tabpanel-performance"
              aria-labelledby="tab-performance"
            >
              <PerformancePage owners={owners} />
            </div>
          }
        />
        <Route
          path="transactions"
          element={
            <div
              role="tabpanel"
              id="tabpanel-transactions"
              aria-labelledby="tab-transactions"
            >
              <TransactionsPage owners={owners} />
            </div>
          }
        />
        <Route
          path="screener"
          element={
            <div role="tabpanel" id="tabpanel-screener" aria-labelledby="tab-screener">
              <Screener />
            </div>
          }
        />
        <Route
          path="query"
          element={
            <div role="tabpanel" id="tabpanel-query" aria-labelledby="tab-query">
              <QueryPage />
            </div>
          }
        />
        <Route
          path="trading"
          element={
            <div role="tabpanel" id="tabpanel-trading" aria-labelledby="tab-trading">
              <TradingAgent />
            </div>
          }
        />
        <Route
          path="timeseries"
          element={
            <div
              role="tabpanel"
              id="tabpanel-timeseries"
              aria-labelledby="tab-timeseries"
            >
              <TimeseriesEdit />
            </div>
          }
        />
        <Route path="*" element={<Navigate to="group" replace />} />
      </Routes>
      <p style={{ marginTop: "2rem", textAlign: "center" }}>
        <a href="/virtual">Virtual Portfolios</a>
        {" • "}
        <a href="/trading">Trading Agent</a>
        {" • "}
        <a href="/support">{t("app.supportLink")}</a>
      </p>
    </div>
  );
}
