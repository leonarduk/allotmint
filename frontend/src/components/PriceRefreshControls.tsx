import { useState } from "react";
import { useTranslation } from "react-i18next";
import { refreshPrices, getPortfolio, getGroupInstruments } from "../api";
import type { Mode } from "../modes";
import type { Portfolio, InstrumentSummary } from "../types";

interface Props {
  mode: Mode;
  selectedOwner: string;
  selectedGroup: string;
  onPortfolio: (p: Portfolio) => void;
  onInstruments: (rows: InstrumentSummary[]) => void;
}

export function PriceRefreshControls({
  mode,
  selectedOwner,
  selectedGroup,
  onPortfolio,
  onInstruments,
}: Props) {
  const { t } = useTranslation();
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const resp = await refreshPrices();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());
      if (mode === "owner" && selectedOwner) {
        onPortfolio(await getPortfolio(selectedOwner));
      } else if (mode === "instrument" && selectedGroup) {
        onInstruments(await getGroupInstruments(selectedGroup));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div style={{ marginBottom: "1rem" }}>
      <button onClick={handleRefresh} disabled={refreshing}>
        {refreshing ? t("app.refreshing") : t("app.refreshPrices")}
      </button>
      {lastRefresh && (
        <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem", color: "#666" }}>
          {t("app.last")}{" "}
          {new Date(lastRefresh).toLocaleString()}
        </span>
      )}
      {error && (
        <span style={{ marginLeft: "0.5rem", color: "red", fontSize: "0.85rem" }}>
          {error}
        </span>
      )}
    </div>
  );
}

export default PriceRefreshControls;

