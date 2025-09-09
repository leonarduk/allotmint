import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getGroupPortfolio } from "../api";
import type { Account, GroupPortfolio } from "../types";
import { translateInstrumentType } from "../lib/instrumentType";
import { money } from "../lib/money";
import { useConfig } from "../ConfigContext";
import { RelativeViewToggle } from "../components/RelativeViewToggle";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff8042",
  "#8dd1e1",
  "#a4de6c",
  "#d0ed57",
  "#ffc0cb",
];

export type AllocationChartsProps = {
  /** Portfolio group slug (defaults to "all"). */
  slug?: string;
};

export function AllocationCharts({ slug = "all" }: AllocationChartsProps) {
  const { t } = useTranslation();
  const { baseCurrency, relativeViewEnabled } = useConfig();
  const [view, setView] = useState<"asset" | "sector" | "region">("asset");
  const [sectorData, setSectorData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const [regionData, setRegionData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const [assetData, setAssetData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // helper to derive a stable key for each account
  const accountKey = (acct: Account, idx: number) =>
    `${acct.owner?.trim() || "unknown"}-${acct.account_type}-${idx}`;

  const toggleAccount = (key: string) =>
    setSelectedAccounts((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );

  useEffect(() => {
    setLoading(true);
    setError(null);
    getGroupPortfolio(slug)
      .then((p: GroupPortfolio) => {
        setPortfolio(p);
        setSelectedAccounts(p.accounts.map(accountKey));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => {
    if (!portfolio) return;
    const activeKeys = selectedAccounts.length
      ? new Set(selectedAccounts)
      : new Set(portfolio.accounts.map(accountKey));
    const activeAccounts = portfolio.accounts.filter((acct, idx) =>
      activeKeys.has(accountKey(acct, idx)),
    );

    const byType: Record<string, number> = {};
    const bySector: Record<string, number> = {};
    const byRegion: Record<string, number> = {};

    for (const acct of activeAccounts) {
      for (const h of acct.holdings) {
        const mv = h.market_value_gbp ?? 0;
        const typeName = translateInstrumentType(t, h.instrument_type);
        byType[typeName] = (byType[typeName] || 0) + mv;
        const sector = h.sector || t("common.other");
        bySector[sector] = (bySector[sector] || 0) + mv;
        const region = h.region || t("common.other");
        byRegion[region] = (byRegion[region] || 0) + mv;
      }
    }

    const asset = Object.entries(byType)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
    const sector = Object.entries(bySector)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
    const region = Object.entries(byRegion)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);

    setAssetData(asset);
    setSectorData(sector);
    setRegionData(region);
  }, [portfolio, selectedAccounts, t]);

  if (loading && !portfolio) return <div>Loading...</div>;

  const chartData =
    view === "asset" ? assetData : view === "sector" ? sectorData : regionData;

  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="container mx-auto p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl md:text-4xl">
          {t("app.modes.allocation", { defaultValue: "Allocation" })}
        </h1>
        <RelativeViewToggle />
      </div>
      <div className="mb-4 flex gap-2">
        <button onClick={() => setView("asset")} disabled={view === "asset"}>
          {t("allocation.instrumentTypes", { defaultValue: "Instrument Types" })}
        </button>
        <button onClick={() => setView("sector")} disabled={view === "sector"}>
          {t("allocation.sector")}
        </button>
        <button onClick={() => setView("region")} disabled={view === "region"}>
          {t("allocation.region")}
        </button>
      </div>
      {portfolio && (
        <div className="mb-4 flex flex-wrap gap-4">
          {portfolio.accounts.map((acct, idx) => {
            const key = accountKey(acct, idx);
            return (
              <label key={key} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={selectedAccounts.includes(key)}
                  onChange={() => toggleAccount(key)}
                />
                {`${acct.owner ?? "—"} - ${acct.account_type}`}
              </label>
            );
          })}
        </div>
      )}
      {error && <p className="text-red-500">{error}</p>}
      <div style={{ width: "100%", height: 400 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius="80%"
              // "percent" may be undefined for empty datasets; default it to 0
              label={({ name, value, percent = 0 }) =>
                relativeViewEnabled
                  ? `${name}: ${(percent * 100).toFixed(2)}%`
                  : `${name}: ${money(value, baseCurrency)} (${(percent * 100).toFixed(2)}%)`
              }
            >
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number, _n: string, item: any) =>
                relativeViewEnabled
                  ? `${
                      total
                        ? ((item?.payload?.value / total) * 100).toFixed(2)
                        : "0.00"
                    }%`
                  : money(v, baseCurrency)
              }
            />
            <Legend
              formatter={(value: string, entry: any) =>
                relativeViewEnabled
                  ? `${value}: ${
                      total
                        ? ((entry?.payload?.value / total) * 100).toFixed(2)
                        : "0.00"
                    }%`
                  : `${value}: ${money(entry?.payload?.value, baseCurrency)}`
              }
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default AllocationCharts;

