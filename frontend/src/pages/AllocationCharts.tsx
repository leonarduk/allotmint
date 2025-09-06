import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getGroupSectorContributions,
  getGroupRegionContributions,
  getGroupPortfolio,
} from "../api";
import type {
  SectorContribution,
  RegionContribution,
  GroupPortfolio,
} from "../types";
import { translateInstrumentType } from "../lib/instrumentType";
import { money } from "../lib/money";
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGroupSectorContributions(slug)
      .then((rows: SectorContribution[]) =>
        setSectorData(
          rows.map((r) => ({
            name: r.sector || t("common.other"),
            value: r.market_value_gbp,
          })),
        ),
      )
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getGroupRegionContributions(slug)
      .then((rows: RegionContribution[]) =>
        setRegionData(
          rows.map((r) => ({
            name: r.region || t("common.other"),
            value: r.market_value_gbp,
          })),
        ),
      )
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getGroupPortfolio(slug)
      .then((p: GroupPortfolio) => {
        const byType: Record<string, number> = {};
        for (const acct of p.accounts) {
          for (const h of acct.holdings) {
            const typeName = translateInstrumentType(t, h.instrument_type);
            const mv = h.market_value_gbp ?? 0;
            byType[typeName] = (byType[typeName] || 0) + mv;
          }
        }
        const data = Object.entries(byType)
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value);
        setAssetData(data);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [slug, t]);

  const chartData =
    view === "asset" ? assetData : view === "sector" ? sectorData : regionData;

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">
        {t("app.modes.allocation", { defaultValue: "Allocation" })}
      </h1>
      <div className="mb-4 flex gap-2">
        <button onClick={() => setView("asset")} disabled={view === "asset"}>
          {t("allocation.instrumentTypes", { defaultValue: "Instrument Types" })}
        </button>
        <button onClick={() => setView("sector")} disabled={view === "sector"}>
          {t("Sector", { defaultValue: "Industries" })}
        </button>
        <button onClick={() => setView("region")} disabled={view === "region"}>
          {t("Region", { defaultValue: "Regions" })}
        </button>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}
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
              label={({ name, value, percent }) =>
                `${name}: ${money(value)} (${(percent * 100).toFixed(2)}%)`
              }
            >
              {chartData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip formatter={(v: number) => money(v)} />
            <Legend
              formatter={(value: string, entry: any) =>
                `${value}: ${money(entry?.payload?.value)}`
              }
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default AllocationCharts;

