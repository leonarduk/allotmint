import { useEffect, useState } from "react";
import { Link, useNavigate, useLocation, useRoutes } from "react-router-dom";
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
import { ComplianceWarnings } from "./components/ComplianceWarnings";
import { ScreenerPage } from "./components/ScreenerPage";

type Mode = "owner" | "group" | "instrument" | "transactions" | "screener";

// derive initial mode + id from path
const path = window.location.pathname.split("/").filter(Boolean);
const initialMode: Mode =
  path[0] === "member" ? "owner" :
  path[0] === "instrument" ? "instrument" :
  path[0] === "transactions" ? "transactions" :
  path[0] === "screener" ? "screener" :
  "group";
const initialSlug = path[1] ?? "";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selectedGroup, setSelectedGroup] = useState(
    initialMode === "instrument" ? initialSlug : ""
  );

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);

  useEffect(() => {
    getOwners().then(setOwners).catch((e) => setErr(String(e)));
    getGroups().then(setGroups).catch((e) => setErr(String(e)));
  }, []);

  // derive route info
  const segments = location.pathname.split("/").filter(Boolean);
  let mode: "owner" | "group" | "instrument" | "transactions" = "group";
  let selectedOwner = "";
  let selectedGroup = "";

  if (segments[0] === "member") {
    mode = "owner";
    selectedOwner = segments[1] ?? "";
  } else if (segments[0] === "instrument") {
    mode = "instrument";
    selectedGroup = segments[1] ?? "";
  } else if (segments[0] === "transactions") {
    mode = "transactions";
  } else {
    mode = "group";
    const params = new URLSearchParams(location.search);
    selectedGroup = params.get("group") ?? "";
  }

  // redirect to defaults if no selection provided
  useEffect(() => {
    if (mode === "owner" && !selectedOwner && owners.length) {
      navigate(`/member/${owners[0].owner}`, { replace: true });
    }
    if (mode === "instrument" && !selectedGroup && groups.length) {
      navigate(`/instrument/${groups[0].slug}`, { replace: true });
    }
    if (mode === "group" && !selectedGroup && groups.length) {
      navigate(`/?group=${groups[0].slug}`, { replace: true });
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

  const routes = useRoutes([
    {
      path: "/member/:owner",
      element: (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={(o) => navigate(`/member/${o}`)}
          />
          <PortfolioView data={portfolio} loading={loading} error={err} />
        </>
      ),
    },
    {
      path: "/instrument/:group",
      element: (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={(g) => navigate(`/instrument/${g}`)}
          />
          {err && <p style={{ color: "red" }}>{err}</p>}
          {loading ? (
            <p>Loading…</p>
          ) : (
            <InstrumentTable rows={instruments} />
          )}
        </>
      ),
    },
    {
      path: "/transactions",
      element: <TransactionsPage owners={owners} />,
    },
    {
      path: "/",
      element: (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={(g) => navigate(`/?group=${g}`)}
          />
          <GroupPortfolioView
            slug={selectedGroup}
            onSelectMember={(owner) => navigate(`/member/${owner}`)}
          />
        </>
      ),
    },
  ]);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <div style={{ marginBottom: "1rem" }}>
        <strong>View by:</strong>{" "}
        {(["group", "instrument", "screener", "owner", "transactions"] as Mode[]).map((m) => (
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
        <Link to={`/?group=${selectedGroup || groups[0]?.slug || ""}`}>Group</Link>{" "}
        <Link
          to={`/instrument/${selectedGroup || groups[0]?.slug || ""}`}
          style={{ marginLeft: "1rem" }}
        >
          Instrument
        </Link>{" "}
        <Link
          to={`/member/${selectedOwner || owners[0]?.owner || ""}`}
          style={{ marginLeft: "1rem" }}
        >
          Member
        </Link>{" "}
        <Link to="/transactions" style={{ marginLeft: "1rem" }}>
          Transactions
        </Link>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? "Refreshing…" : "Refresh Prices"}
        </button>
        {lastPriceRefresh && (
          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
            Last: {new Date(lastPriceRefresh).toLocaleString()}
          </span>
        )}
        {priceRefreshError && (
          <span style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}>
            {priceRefreshError}
          </span>
        )}
      </div>

      {routes}
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
      {mode === "group" && (
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
              window.history.pushState({}, "", `/member/${owner}`);
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

      {mode === "transactions" && <TransactionsPage owners={owners} />}

      {mode === "screener" && <ScreenerPage />}
    </div>
  );
}

