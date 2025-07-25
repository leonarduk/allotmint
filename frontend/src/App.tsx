// src/App.tsx
import React, { useEffect, useState } from "react";
import {
  getOwners,
  getPortfolio,
  getGroups,
  refreshPrices,
} from "./api";
import type {
  OwnerSummary,
  Portfolio,
  GroupSummary
} from "./types";
import { OwnerSelector } from "./components/OwnerSelector";
import { GroupSelector } from "./components/GroupSelector";
import { PortfolioView } from "./components/PortfolioView";
import { GroupPortfolioView } from "./components/GroupPortfolioView";

type Mode = "owner" | "group";

function App() {
  const [mode, setMode] = useState<Mode>("owner");

  /* ─ owners ──────────────────────────────────────────────── */
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [selectedOwner, setSelectedOwner] = useState("");

  /* ─ groups ──────────────────────────────────────────────── */
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");

  /* ─ data caches (used only in owner mode) ───────────────── */
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  /* ─ price refresh state ─────────────────────────────────── */
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(
    null
  );
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(
    null
  );

  /* ─────────────────────────────────────────────────────────
     Initial data load
     ───────────────────────────────────────────────────────── */
  useEffect(() => {
    getOwners().then(setOwners).catch((e) => setErr(String(e)));
    getGroups().then(setGroups).catch((e) => setErr(String(e)));
  }, []);

  /* Default selection after owners/groups arrive */
  useEffect(() => {
    if (!selectedOwner && owners.length) setSelectedOwner(owners[0].owner);
    if (!selectedGroup && groups.length) setSelectedGroup(groups[0].slug);
  }, [owners, groups]);

  /* Load portfolio for the selected owner */
  useEffect(() => {
    if (mode !== "owner" || !selectedOwner) return;
    setLoading(true);
    setErr(null);
    getPortfolio(selectedOwner)
      .then(setPortfolio)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [mode, selectedOwner]);

  /* ─ Refresh prices ─ */
  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    setPriceRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastPriceRefresh(resp.timestamp ?? new Date().toISOString());

      if (mode === "owner" && selectedOwner) {
        const p = await getPortfolio(selectedOwner);
        setPortfolio(p);
      } else if (mode === "group" && selectedGroup) {
        // force GroupPortfolioView to refetch by clearing key
        setSelectedGroup("");            // trigger unmount
        setTimeout(() => setSelectedGroup(resp.group ?? selectedGroup), 0);
      }
    } catch (e) {
      setPriceRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshingPrices(false);
    }
  }

  /* Callback from GroupPortfolioView when user clicks a member */
  function handleSelectMemberFromGroup(owner: string) {
    setMode("owner");
    setSelectedOwner(owner);
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      {/* Mode toggle */}
      <div style={{ marginBottom: "1rem" }}>
        <strong>View by:</strong>{" "}
        <label>
          <input
            type="radio"
            name="mode"
            value="owner"
            checked={mode === "owner"}
            onChange={() => setMode("owner")}
          />{" "}
          Owner
        </label>{" "}
        <label>
          <input
            type="radio"
            name="mode"
            value="group"
            checked={mode === "group"}
            onChange={() => setMode("group")}
          />{" "}
          Group
        </label>
      </div>

      {/* Price refresh button */}
      <div style={{ marginBottom: "1rem" }}>
        <button onClick={handleRefreshPrices} disabled={refreshingPrices}>
          {refreshingPrices ? "Refreshing…" : "Refresh Prices"}
        </button>
        {lastPriceRefresh && (
          <span
            style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}
          >
            Last: {new Date(lastPriceRefresh).toLocaleString()}
          </span>
        )}
        {priceRefreshError && (
          <span
            style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}
          >
            {priceRefreshError}
          </span>
        )}
      </div>

      {/* Owner view */}
      {mode === "owner" && (
        <>
          <OwnerSelector
            owners={owners}
            selected={selectedOwner}
            onSelect={setSelectedOwner}
          />
          <PortfolioView data={portfolio} loading={loading} error={err} />
        </>
      )}

      {/* Group view */}
      {mode === "group" && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={setSelectedGroup}
          />
          {selectedGroup ? (
            <GroupPortfolioView
              slug={selectedGroup}
              onSelectMember={handleSelectMemberFromGroup}
            />
          ) : (
            <p>Select a group.</p>
          )}
        </>
      )}
    </div>
  );
}

export default App;
