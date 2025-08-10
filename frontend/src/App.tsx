import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
  | "timeseries";

// derive initial mode + id from path
const path = window.location.pathname.split("/").filter(Boolean);
const initialMode: Mode =
  path[0] === "member" ? "owner" :
  path[0] === "instrument" ? "instrument" :
  path[0] === "transactions" ? "transactions" :
  path[0] === "performance" ? "performance" :
  path[0] === "screener" ? "screener" :
  path[0] === "timeseries" ? "timeseries" :
  "group";
const initialSlug = path[1] ?? "";

export default function App() {
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedOwner, setSelectedOwner] = useState(
    initialMode === "owner" ? initialSlug : "",
  );
  const params = new URLSearchParams(window.location.search);
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
  // Toggle between showing absolute or relative positions in holdings tables
  const [relativeView, setRelativeView] = useState(true);

  useEffect(() => {
    getOwners().then(setOwners).catch((e) => setErr(String(e)));
    getGroups().then(setGroups).catch((e) => setErr(String(e)));
  }, []);
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


  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <LanguageSwitcher />
      <AlertsPanel />
      {/* mode toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <strong>View by:</strong>{" "}
        {([
          "group",
          "instrument",
          "owner",
          "performance",
          "transactions",
          "screener",
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
            {m === "owner"
              ? "Member"
              : m.charAt(0).toUpperCase() + m.slice(1)}
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
          Relative view
        </label>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? "Refreshing…" : "Refresh Prices"}
        </button>
        {lastPriceRefresh && (
          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
            Last: {new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(lastPriceRefresh))}
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
      {mode === "group" && (
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
      {mode === "instrument" && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={setSelectedGroup}
          />
          {err && <p style={{ color: "red" }}>{err}</p>}
          {loading ? (
            <p>Loading…</p>
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

      <p style={{ marginTop: "2rem", textAlign: "center" }}>
        <a href="/support">Support</a>
      </p>
    </div>
  );
}

