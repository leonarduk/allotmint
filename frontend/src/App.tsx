import { useEffect, useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getGroupInstruments, getGroups, getOwners, getPortfolio, refreshPrices } from "./api";

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
import { TimeseriesEdit } from "./pages/TimeseriesEdit";
import Watchlist from "./pages/Watchlist";
import TopMovers from "./pages/TopMovers";
import { useConfig } from "./ConfigContext";

type Mode =
  | "owner"
  | "group"
  | "instrument"
  | "transactions"
  | "performance"
  | "screener"
  | "query"
  | "timeseries"
  | "groupInstrumentMemberTimeseries"
  | "watchlist"
  | "movers"
  | "support";

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
  path[0] === "groupInstrumentMemberTimeseries" ? "groupInstrumentMemberTimeseries" :
  path[0] === "watchlist" ? "watchlist" :
  path[0] === "movers" ? "movers" :
  path[0] === "support" ? "support" :
  "group";
const initialSlug = path[1] ?? "";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs } = useConfig();

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

  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);
  const [backendUnavailable, setBackendUnavailable] = useState(false);

  const ownersReq = useFetchWithRetry(getOwners);
  const groupsReq = useFetchWithRetry(getGroups);

  const modes: Mode[] = [
    "group",
    "instrument",
    "owner",
    "performance",
    "transactions",
    "screener",
    "query",
    "timeseries",
    "groupInstrumentMemberTimeseries",
    "watchlist",
    "movers",
    "support",
  ];

  function pathFor(m: Mode) {
    switch (m) {
      case "group":
        return selectedGroup ? `/?group=${selectedGroup}` : "/";
      case "instrument":
        return selectedGroup ? `/instrument/${selectedGroup}` : "/instrument";
      case "owner":
        return selectedOwner ? `/member/${selectedOwner}` : "/member";
      case "performance":
        return selectedOwner ? `/performance/${selectedOwner}` : "/performance";
      case "movers":
        return "/movers";
      default:
        return `/${m}`;
    }
  }

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
            : segs[0] === "groupInstrumentMemberTimeseries"
              ? "groupInstrumentMemberTimeseries"
              : segs[0] === "watchlist"
                ? "watchlist"
                : segs[0] === "movers"
                  ? "movers"
                : segs[0] === "support"
                  ? "support"
                  : "group";
    if (tabs[newMode] === false) {
      setMode("group");
      navigate("/", { replace: true });
      return;
    }
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
  }, [location.pathname, location.search, tabs, navigate]);

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
      <nav style={{ margin: "1rem 0" }}>
        {modes
          .filter((m) => tabs[m] !== false)
          .map((m) => (
            <Link
              key={m}
              to={pathFor(m)}
              style={{
                marginRight: "1rem",
                fontWeight: mode === m ? "bold" : undefined,
              }}
            >
              {t(`app.modes.${m}`)}
            </Link>
          ))}
      </nav>

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
      {mode === "watchlist" && <Watchlist />}
      {mode === "movers" && <TopMovers />}

      {mode === "query" && <QueryPage />}

    </div>
  );
}

