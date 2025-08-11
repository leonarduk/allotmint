import { useEffect, useState } from "react";
import { OwnerSelector } from "../components/OwnerSelector";
import { PortfolioView } from "../components/PortfolioView";
import { ComplianceWarnings } from "../components/ComplianceWarnings";
import { getPortfolio, refreshPrices } from "../api";
import type { OwnerSummary, Portfolio } from "../types";
import { useTranslation } from "react-i18next";

interface Props {
  owners: OwnerSummary[];
  relativeView: boolean;
}

export default function OwnerPage({ owners, relativeView }: Props) {
  const { t } = useTranslation();
  const [selectedOwner, setSelectedOwner] = useState("");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedOwner && owners.length) {
      setSelectedOwner(owners[0].owner);
    }
  }, [owners, selectedOwner]);

  useEffect(() => {
    if (selectedOwner) {
      setLoading(true);
      setErr(null);
      getPortfolio(selectedOwner)
        .then(setPortfolio)
        .catch((e) => setErr(String(e)))
        .finally(() => setLoading(false));
    }
  }, [selectedOwner]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const resp = await refreshPrices();
      setLastRefresh(resp.timestamp ?? new Date().toISOString());
      if (selectedOwner) {
        setPortfolio(await getPortfolio(selectedOwner));
      }
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <>
      <OwnerSelector owners={owners} selected={selectedOwner} onSelect={setSelectedOwner} />
      <ComplianceWarnings owners={selectedOwner ? [selectedOwner] : []} />
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
      <PortfolioView
        data={portfolio}
        loading={loading}
        error={err}
        relativeView={relativeView}
      />
    </>
  );
}
