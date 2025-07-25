import React, { useEffect, useState } from "react";
import {
  getOwners,
  getPortfolio,
  getGroups,
  refreshPrices,
  getGroupInstruments,
} from "./api";
import type {
  OwnerSummary,
  Portfolio,
  GroupSummary,
  InstrumentSummary,
} from "./types";
import { OwnerSelector } from "./components/OwnerSelector";
import { GroupSelector } from "./components/GroupSelector";
import { PortfolioView } from "./components/PortfolioView";
import { GroupPortfolioView } from "./components/GroupPortfolioView";
import { InstrumentTable } from "./components/InstrumentTable";

type Mode = "owner" | "group" | "instrument";

function App() {
  const [mode, setMode] = useState<Mode>("owner");

  /* owners --------------------------------------------------- */
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [selectedOwner, setSelectedOwner] = useState("");

  /* groups --------------------------------------------------- */
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");

  /* data state ---------------------------------------------- */
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  /* price refresh ------------------------------------------- */
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);

  /* initial fetch ------------------------------------------- */
  useEffect(() => {
    getOwners().then(setOwners).catch((e) => setErr(String(e)));
    getGroups().then(setGroups).catch((e) => setErr(String(e)));
  }, []);

  /* defaults ------------------------------------------------ */
  useEffect(() => {
    if (!selectedOwner && owners.length) setSelectedOwner(owners[0].owner);
    if (!selectedGroup && groups.length) setSelectedGroup(groups[0].slug);
  }, [owners, groups]);

  /* owner portfolio fetch ----------------------------------- */
  useEffect(() => {
    if (mode !== "owner" || !selectedOwner) return;
    setLoading(true);
    setErr(null);
    getPortfolio(selectedOwner)
      .then(setPortfolio)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [mode, selectedOwner]);

  /* group instruments fetch --------------------------------- */
  useEffect(() => {
    if (mode !== "instrument" || !selectedGroup) return;
    setLoading(true);
    setErr(null);
    getGroupInstruments(selectedGroup)
      .then(setInstruments)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [mode, selectedGroup]);

  /* price refresh ------------------------------------------- */
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

  /* --------------------------------------------------------- */
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      {/* mode toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <strong>View by:</strong>{" "}
        {(["owner", "group", "instrument"] as Mode[]).map((m) => (
          <label key={m} style={{ marginRight: "1rem" }}>
            <input
              type="radio"
              name="mode"
              value={m}
              checked={mode === m}
              onChange={() => setMode(m)}
            />{" "}
            {m.charAt(0).toUpperCase() + m.slice(1)}
          </label>
        ))}
      </div>

      {/* price refresh */}
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

      {/* owner view */}
      {mode === "owner" && (
        <>
          <OwnerSelector owners={owners} selected={selectedOwner} onSelect={setSelectedOwner} />
          <PortfolioView data={portfolio} loading={loading} error={err} />
        </>
      )}

      {/* group view */}
      {mode === "group" && (
        <>
          <GroupSelector groups={groups} selected={selectedGroup} onSelect={setSelectedGroup} />
          <GroupPortfolioView slug={selectedGroup} onSelectMember={setSelectedOwner} />
        </>
      )}

      {/* instrument view */}
      {mode === "instrument" && (
        <>
          <GroupSelector groups={groups} selected={selectedGroup} onSelect={setSelectedGroup} />
          {err && <p style={{ color: "red" }}>{err}</p>}
          {loading ? <p>Loading…</p> : <InstrumentTable rows={instruments} />}
        </>
      )}
    </div>
  );
}

export default App;
