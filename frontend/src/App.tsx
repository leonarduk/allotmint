import { useEffect, useState } from "react";
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
import { PerformanceDashboard } from "./components/PerformanceDashboard";

import { AlertsPanel } from "./components/AlertsPanel";
import { ComplianceWarnings } from "./components/ComplianceWarnings";
import { Screener } from "./pages/Screener";
import { QueryPage } from "./pages/QueryPage";
import useFetchWithRetry from "./hooks/useFetchWithRetry";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import i18n from "./i18n";
import { TimeseriesEdit } from "./pages/TimeseriesEdit";

type Mode =
  | "owner"
  | "group"
  | "instrument"
  | "transactions"
  | "performance"
  | "screener"
  | "query"
  | "timeseries";

// derive initial mode + id from path
const path = window.location.pathname.split("/").filter(Boolean);
const initialMode: Mode =
  path[0] === "member" ? "owner" :
  path[0] === "instrument" ? "instrument" :
  path[0] === "transactions" ? "transactions" :
  path[0] === "performance" ? "performance" :
  path[0] === "screener" ? "screener" :
  path[0] === "query" ? "query" :
  path[0] === "timeseries" ? "timeseries" :
  "group";
const initialSlug = path[1] ?? "";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const params = new URLSearchParams(location.search);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedOwner, setSelectedOwner] = useState(
    initialMode === "owner" ? initialSlug : "",
  );
  const [selectedGroup, setSelectedGroup] = useState(
    initialMode === "instrument" ? initialSlug : params.get("group") ?? "",
  );

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // when true, holdings table emphasises relative metrics
  const [relativeView, setRelativeView] = useState(true);

  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);
  const [backendUnavailable, setBackendUnavailable] = useState(false);

  const ownersReq = useFetchWithRetry(getOwners);
  const groupsReq = useFetchWithRetry(getGroups);

  useEffect(() => {
    const segs = location.pathname.split("/").filter(Boolean);
    const newMode: Mode =
      segs[0] === "member"
        ? "owner"
        : segs[0] === "instrument"
          ? "instrument"
          : segs[0] === "transactions"
            ? "transactions"
            : segs[0] === "performance"
              ? "performance"
              : segs[0] === "screener"
                ? "screener"
                : segs[0] === "query"
                  ? "query"
                  : segs[0] === "timeseries"
                    ? "timeseries"
                    : "group";
    setMode(newMode);
    if (newMode === "owner") {
      setSelectedOwner(segs[1] ?? "");
    } else if (newMode === "instrument") {
      setSelectedGroup(segs[1] ?? "");
    } else if (newMode === "group") {
      setSelectedGroup(
        new URLSearchParams(location.search).get("group") ?? "",
      );
    }
  }, [location.pathname, location.search]);

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
      setLastPriceRefresh(resp.timestamp ?? new Date().toISOString());

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
      {/* mode toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <strong>{t("app.viewBy")}</strong>{" "}
        {([
          "group",
          "instrument",
          "owner",
          "performance",
          "transactions",
          "screener",
          "query",
          "timeseries",
        ] as Mode[]).map((m) => (
          <label key={m} style={{ marginRight: "1rem" }}>
            <input
              type="radio"
              name="mode"
              value={m}
              checked={mode === m}
              onChange={() => setMode(m)}
            />{" "}
            {t(`app.modes.${m}`)}
          </label>
        ))}
      </div>

      {/* absolute vs relative toggle */}
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

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? t("app.refreshing") : t("app.refreshPrices")}
        </button>
        {lastPriceRefresh && (
          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
            {t("app.last")}{" "}
            {new Date(lastPriceRefresh).toLocaleString()}
          </span>
        )}
        {priceRefreshError && (
          <span style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}>
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
            onSelect={setSelectedOwner}
          />
          <ComplianceWarnings owners={selectedOwner ? [selectedOwner] : []} />
          <PortfolioView
            data={portfolio}
            loading={loading}
            error={err}
            relativeView={relativeView}
          />
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
          <label style={{ display: "block", margin: "0.5rem 0" }}>
            <input
              type="checkbox"
              checked={relativeView}
              onChange={(e) => setRelativeView(e.target.checked)}
            />{" "}
            Relative view
          </label>
          <ComplianceWarnings
            owners={
              groups.find((g) => g.slug === selectedGroup)?.members ?? []
            }
          />
          <GroupPortfolioView
            slug={selectedGroup}
            relativeView={relativeView}
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
          {loading ? (
            <p>{t("app.loading")}</p>
          ) : (
            <InstrumentTable rows={instruments} />
          )}
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

      {mode === "screener" && <Screener />}
      {mode === "timeseries" && <TimeseriesEdit />}

      {mode === "query" && <QueryPage />}

      <p style={{ marginTop: "2rem", textAlign: "center" }}>
        <a href="/virtual">Virtual Portfolios</a>
        {" • "}
        <a href="/support">{t("app.supportLink")}</a>
      </p>
    </div>
  );
}

