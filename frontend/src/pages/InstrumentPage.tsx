import { useEffect, useState } from "react";
import { GroupSelector } from "../components/GroupSelector";
import { InstrumentTable } from "../components/InstrumentTable";
import { getGroupInstruments, refreshPrices } from "../api";
import type { GroupSummary, InstrumentSummary } from "../types";
import { useTranslation } from "react-i18next";

interface Props {
  groups: GroupSummary[];
}

export default function InstrumentPage({ groups }: Props) {
  const { t } = useTranslation();
  const [selectedGroup, setSelectedGroup] = useState("");
  const [instruments, setInstruments] = useState<InstrumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedGroup && groups.length) {
      setSelectedGroup(groups[0].slug);
    }
  }, [groups, selectedGroup]);

  useEffect(() => {
    if (selectedGroup) {
      setLoading(true);
      setErr(null);
      getGroupInstruments(selectedGroup)
        .then(setInstruments)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [selectedGroup]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());
      if (selectedGroup) {
        setInstruments(await getGroupInstruments(selectedGroup));
      }
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <>
      <GroupSelector
        groups={groups}
        selected={selectedGroup}
        onSelect={setSelectedGroup}
      />
      {err && <p style={{ color: "red" }}>{err}</p>}
      <div style={{ margin: "1rem 0" }}>
        <button onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? t("app.refreshing") : t("app.refreshPrices")}
        </button>
        {lastRefresh && (
          <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
            {t("app.last")}{" "}
            {new Date(lastRefresh).toLocaleString()}
          </span>
        )}
        {refreshError && (
          <span style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}>
            {refreshError}
          </span>
        )}
      </div>
      {loading ? <p>{t("app.loading")}</p> : <InstrumentTable rows={instruments} />}
    </>
  );
}
