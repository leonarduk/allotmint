import { useState } from "react";
import { useTranslation } from "react-i18next";
import { clearGroupInstrumentCache, refreshPrices } from "../api";
import { localDateISO } from "../lib/date";
import { pricingFreshness } from "../lib/pricingFreshness";
import { clearFetchCache } from "../utils/fetchCache";

type PricingAsOfProps = {
  /** ISO `YYYY-MM-DD` date the portfolio was priced at. */
  pricingDate: string;
  /** True when the user deliberately picked a historical pricing date. */
  historical: boolean;
  /** Re-load the portfolio once fresh prices have been fetched. */
  onRefreshed: () => void;
  /** Injectable "today" for tests; defaults to the browser's local date. */
  today?: string;
};

/**
 * Dashboard "Pricing as of <date>" line (#7820). When the date is older than
 * the last expected market close it is flagged with its age and a refresh
 * button, so stale valuations aren't presented with the same weight as
 * current ones. A deliberately chosen historical date is never flagged.
 */
export function PricingAsOf({
  pricingDate,
  historical,
  onRefreshed,
  today = localDateISO(),
}: PricingAsOfProps) {
  const { t } = useTranslation();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const freshness = historical
    ? { stale: false as const }
    : pricingFreshness(pricingDate, today);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await refreshPrices();
      // Every cached valuation was computed against the old prices.
      clearFetchCache();
      clearGroupInstrumentCache();
      onRefreshed();
    } catch (e) {
      setRefreshError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div
      style={{
        marginTop: "0.25rem",
        fontSize: "0.85rem",
        color: "var(--summary-card-label)",
      }}
    >
      <span>{t("group.pricingAsOf", { date: pricingDate })}</span>
      {freshness.stale && (
        <span
          role="status"
          className="text-amber-400"
          style={{ marginLeft: "0.5rem", fontWeight: 600 }}
        >
          {t("group.pricingStale", { count: freshness.ageDays })}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            style={{ marginLeft: "0.5rem", fontSize: "0.75rem" }}
          >
            {refreshing ? t("app.refreshing") : t("app.refreshPrices")}
          </button>
        </span>
      )}
      {refreshError && (
        <div role="alert" className="text-amber-400">
          {t("group.pricingRefreshError", { detail: refreshError })}
        </div>
      )}
    </div>
  );
}

export default PricingAsOf;
