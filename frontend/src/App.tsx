import React, { useEffect, useState } from "react";
import { getOwners, getPortfolio, getGroups, getGroupPortfolio, refreshPrices } from "./api";
import type { OwnerSummary, Portfolio, GroupSummary, GroupPortfolio } from "./types";
import { OwnerSelector } from "./components/OwnerSelector";
import { GroupSelector } from "./components/GroupSelector";
import { PortfolioView } from "./components/PortfolioView";
import { GroupPortfolioView } from "./components/GroupPortfolioView";

type Mode = "owner" | "group";

function App() {
  const [mode, setMode] = useState<Mode>("owner");

  // owners
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [selectedOwner, setSelectedOwner] = useState<string>("");

  // groups
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>("");

  // data
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [groupPortfolio, setGroupPortfolio] = useState<GroupPortfolio | null>(null);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [lastPriceRefresh, setLastPriceRefresh] = useState<string | null>(null);
  const [priceRefreshError, setPriceRefreshError] = useState<string | null>(null);

  // load owners + groups on mount
  useEffect(() => {
    getOwners().then(setOwners).catch((e) => setErr(String(e)));
    getGroups().then(setGroups).catch((e) => setErr(String(e)));
  }, []);

  // default selections once data loads
  useEffect(() => {
    if (!selectedOwner && owners.length) setSelectedOwner(owners[0].owner);
    if (!selectedGroup && groups.length) setSelectedGroup(groups[0].group);
  }, [owners, groups]);

  // load selected owner
  useEffect(() => {
    if (mode !== "owner" || !selectedOwner) return;
    setLoading(true);
    setErr(null);
    getPortfolio(selectedOwner)
      .then(setPortfolio)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [mode, selectedOwner]);

  // load selected group
  useEffect(() => {
    if (mode !== "group" || !selectedGroup) return;
    setLoading(true);
    setErr(null);
    getGroupPortfolio(selectedGroup)
      .then(setGroupPortfolio)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [mode, selectedGroup]);

async function handleRefreshPrices() {
  setRefreshingPrices(true);
  setPriceRefreshError(null);
  try {
    const resp = await refreshPrices();
    setLastPriceRefresh(resp.timestamp ?? new Date().toISOString());
    // re-fetch whichever mode we're in
    if (mode === "owner" && selectedOwner) {
      const p = await getPortfolio(selectedOwner);
      setPortfolio(p);
    } else if (mode === "group" && selectedGroup) {
      const gp = await getGroupPortfolio(selectedGroup);
      setGroupPortfolio(gp);
    }
} catch (e) {
  setPriceRefreshError(e instanceof Error ? e.message : String(e));
  } finally {
    setRefreshingPrices(false);
  }
}

  // callback when clicking member row in group view
  function handleSelectMemberFromGroup(owner: string) {
    setMode("owner");
    setSelectedOwner(owner);
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
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

      {mode === "group" && (
        <>
          <GroupSelector
            groups={groups}
            selected={selectedGroup}
            onSelect={setSelectedGroup}
          />
          <GroupPortfolioView
            data={groupPortfolio}
            loading={loading}
            error={err}
            onSelectMember={handleSelectMemberFromGroup}
          />
        </>
      )}
    </div>
  );
}

export default App;
