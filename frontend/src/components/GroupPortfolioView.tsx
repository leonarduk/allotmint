// src/components/GroupPortfolioView.tsx
import { useState, useEffect, useCallback } from "react";

import type {
  GroupPortfolio,
  Account,
  SectorContribution,
  RegionContribution,
} from "../types";
import {
  getGroupPortfolio,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupMaxDrawdown,getGroupSectorContributions,
  getGroupRegionContributions,
} from "../api";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { TopMoversSummary } from "./TopMoversSummary";
import { money, percent } from "../lib/money";
import PortfolioSummary, { computePortfolioTotals } from "./PortfolioSummary";
import { translateInstrumentType } from "../lib/instrumentType";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { RelativeViewToggle } from "./RelativeViewToggle";
import metricStyles from "../styles/metrics.module.css";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
} from "recharts";

const PIE_COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff8042",
  "#8dd1e1",
  "#a4de6c",
  "#d0ed57",
  "#ffc0cb",
];

type SelectedInstrument = {
  ticker: string;
  name: string;
};

type Props = {
  slug: string;
  /** when clicking an owner you may want to jump to the member tab */
  onSelectMember?: (owner: string) => void;
  onTradeInfo?: (info: { trades_this_month?: number; trades_remaining?: number } | null) => void;
};

/* ────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────── */
export function GroupPortfolioView({ slug, onSelectMember, onTradeInfo }: Props) {
  const fetchPortfolio = useCallback(() => getGroupPortfolio(slug), [slug]);
  const { data: portfolio, loading, error } = useFetch<GroupPortfolio>(
    fetchPortfolio,
    [slug],
    !!slug
  );
  const fetchSector = useCallback(() => getGroupSectorContributions(slug), [slug]);
  const fetchRegion = useCallback(() => getGroupRegionContributions(slug), [slug]);
  const { data: sectorContrib } = useFetch<SectorContribution[]>(
    fetchSector,
    [slug],
    !!slug
  );
  const { data: regionContrib } = useFetch<RegionContribution[]>(
    fetchRegion,
    [slug],
    !!slug
  );
  const [selected, setSelected] = useState<SelectedInstrument | null>(null);
  const { t } = useTranslation();
  const { relativeViewEnabled } = useConfig();
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null);
  const [contribTab, setContribTab] = useState<"sector" | "region">("sector");

  // helper to derive a stable key for each account
  const accountKey = (acct: Account, idx: number) =>
    `${acct.owner ?? "owner"}-${acct.account_type}-${idx}`;

  // when portfolio changes, select all accounts by default
  useEffect(() => {
    if (portfolio?.accounts) {
      setSelectedAccounts(portfolio.accounts.map(accountKey));
    }
  }, [portfolio]);

  useEffect(() => {
    if (!slug) return;
    Promise.all([
      getGroupAlphaVsBenchmark(slug, "VWRL.L"),
      getGroupTrackingError(slug, "VWRL.L"),
      getGroupMaxDrawdown(slug),
    ])
      .then(([a, te, md]) => {
        setAlpha(a.alpha_vs_benchmark);
        setTrackingError(te.tracking_error);
        setMaxDrawdown(md.max_drawdown);
      })
      .catch(() => {});
  }, [slug]);

  useEffect(() => {
    if (onTradeInfo) {
      onTradeInfo(
        portfolio
          ? {
              trades_this_month: portfolio.trades_this_month,
              trades_remaining: portfolio.trades_remaining,
            }
          : null,
      );
    }
  }, [portfolio, onTradeInfo]);

  /* ── early‑return states ───────────────────────────────── */
  if (!slug) return <p>{t("group.select")}</p>;
  if (error)
    return <p className="text-red-500">{t("common.error")}: {error.message}</p>;
  if (loading || !portfolio) return <p>{t("common.loading")}</p>;

  const perOwner: Record<
    string,
    { value: number; dayChange: number; gain: number; cost: number }
  > = {};
  const perType: Record<string, number> = {};

  const activeKeys = selectedAccounts.length
    ? new Set(selectedAccounts)
    : new Set(portfolio.accounts?.map(accountKey));

  const activeAccounts = (portfolio.accounts ?? []).filter((acct, idx) =>
    activeKeys.has(accountKey(acct, idx))
  );

  const totals = computePortfolioTotals(activeAccounts);
  const { totalValue } = totals;

  for (const acct of activeAccounts) {
    const owner = acct.owner ?? "—";
    const entry =
      perOwner[owner] || (perOwner[owner] = { value: 0, dayChange: 0, gain: 0, cost: 0 });

    entry.value += acct.value_estimate_gbp ?? 0;

    for (const h of acct.holdings ?? []) {
      const cost =
        h.cost_basis_gbp && h.cost_basis_gbp > 0
          ? h.cost_basis_gbp
          : h.effective_cost_basis_gbp ?? 0;
      const market = h.market_value_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;
      const dayChg = h.day_change_gbp ?? 0;

      const typeKey = (h.instrument_type ?? "other").toLowerCase();
      perType[typeKey] = (perType[typeKey] || 0) + market;

      entry.cost += cost;
      entry.gain += gain;
      entry.dayChange += dayChg;
    }
  }

  const ownerRows = Object.entries(perOwner).map(([owner, data]) => {
    const gainPct = data.cost > 0 ? (data.gain / data.cost) * 100 : 0;
    const dayChangePct =
      data.value - data.dayChange !== 0
        ? (data.dayChange / (data.value - data.dayChange)) * 100
        : 0;
    const valuePct = totalValue > 0 ? (data.value / totalValue) * 100 : 0;
    return { owner, ...data, gainPct, dayChangePct, valuePct };
  });

  const typeRows = Object.entries(perType).map(([type, value]) => ({
    name: translateInstrumentType(t, type),
    value,
    pct: totalValue > 0 ? (value / totalValue) * 100 : 0,
  }));

  /* ── render ────────────────────────────────────────────── */
  return (
    <div className="mt-4">
      <div className="flex justify-between items-center">
        <h2>{portfolio.name}</h2>
        <RelativeViewToggle />
      </div>

      {!relativeViewEnabled && <PortfolioSummary totals={totals} />}

      <div className={metricStyles.metricContainer}>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Alpha vs Benchmark</div>
          <div className={metricStyles.metricValue}>
            {percent(alpha != null ? alpha * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Tracking Error</div>
          <div className={metricStyles.metricValue}>
            {percent(trackingError != null ? trackingError * 100 : null)}
          </div>
        </div>
        <div className={metricStyles.metricCard}>
          <div className={metricStyles.metricLabel}>Max Drawdown</div>
          <div className={metricStyles.metricValue}>
            {percent(maxDrawdown != null ? maxDrawdown * 100 : null)}
          </div>
        </div>
      </div>

      {typeRows.length > 0 && (
        <div className="w-full h-60 my-4">
          <ResponsiveContainer>
            <PieChart>
              <Pie
                dataKey="value"
                data={typeRows}
                label={({ name, pct }) => `${name} ${percent(pct)}`}
              >
                {typeRows.map((_, idx) => (
                  <Cell
                    key={`cell-${idx}`}
                    fill={PIE_COLORS[idx % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v: number, n: string) => [money(v), n]} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {(sectorContrib?.length || regionContrib?.length) && (
        <div className="w-full h-[300px] my-4">
          <div className="mb-2">
            <button
              onClick={() => setContribTab("sector")}
              disabled={contribTab === "sector"}
              className="mr-2"
            >
              Sector
            </button>
            <button
              onClick={() => setContribTab("region")}
              disabled={contribTab === "region"}
            >
              Region
            </button>
          </div>
          <ResponsiveContainer>
            <BarChart
              data={
                contribTab === "sector"
                  ? sectorContrib || []
                  : regionContrib || []
              }
            >
              <XAxis dataKey={contribTab === "sector" ? "sector" : "region"} />
              <YAxis />
              <Tooltip formatter={(v: number) => money(v)} />
              <Bar dataKey="gain_gbp">
                {(contribTab === "sector" ? sectorContrib : regionContrib)?.map(
                  (row, idx) => (
                    <Cell
                      key={`cell-bar-${idx}`}
                      fill={row.gain_gbp >= 0 ? "lightgreen" : "red"}
                    />
                  )
                )}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <TopMoversSummary slug={slug} />

      {/* Per-owner summary */}
      <table className={`${tableStyles.table} mb-4`}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Owner</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              {relativeViewEnabled ? "Portfolio %" : "Total Value"}
            </th>
            {!relativeViewEnabled && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Day Change</th>
            )}
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Day Change %</th>
            {!relativeViewEnabled && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total Gain</th>
            )}
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total Gain %</th>
          </tr>
        </thead>
        <tbody>
          {ownerRows.map((row) => (
            <tr key={row.owner}>
              <td
                className={`${tableStyles.cell} ${
                  onSelectMember ? tableStyles.clickable : ""
                }`}
                onClick={
                  onSelectMember ? () => onSelectMember(row.owner) : undefined
                }
              >
                {row.owner}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                {relativeViewEnabled ? percent(row.valuePct) : money(row.value)}
              </td>
              {!relativeViewEnabled && (
                <td
                  className={`${tableStyles.cell} ${tableStyles.right} ${
                    row.dayChange >= 0 ? "text-[lightgreen]" : "text-red-500"
                  }`}
                >
                  {money(row.dayChange)}
                </td>
              )}
              <td
                className={`${tableStyles.cell} ${tableStyles.right} ${
                  row.dayChange >= 0 ? "text-[lightgreen]" : "text-red-500"
                }`}
              >
                {percent(row.dayChangePct)}
              </td>
              {!relativeViewEnabled && (
                <td
                  className={`${tableStyles.cell} ${tableStyles.right} ${
                    row.gain >= 0 ? "text-[lightgreen]" : "text-red-500"
                  }`}
                >
                  {money(row.gain)}
                </td>
              )}
              <td
                className={`${tableStyles.cell} ${tableStyles.right} ${
                  row.gain >= 0 ? "text-[lightgreen]" : "text-red-500"
                }`}
              >
                {percent(row.gainPct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Account breakdown */}
      {portfolio.accounts?.map((acct, idx) => {
        const key = accountKey(acct, idx);
        const checked = activeKeys.has(key);
        return (
          <div key={key} className="mb-6">
            <h3>
              <input
                type="checkbox"
                checked={checked}
                onChange={() =>
                  setSelectedAccounts((prev) =>
                    prev.includes(key)
                      ? prev.filter((k) => k !== key)
                      : [...prev, key]
                  )
                }
                aria-label={`${acct.owner ?? "—"} ${acct.account_type}`}
                className="mr-2"
              />
              {onSelectMember ? (
                <span
                  className={tableStyles.clickable}
                  onClick={() => onSelectMember(acct.owner ?? "—")}
                >
                  {acct.owner ?? "—"}
                </span>
              ) : (
                <>{acct.owner ?? "—"}</>
              )}{" "}
              • {acct.account_type} — {money(acct.value_estimate_gbp)}
            </h3>

            {checked && (
              <HoldingsTable
                holdings={acct.holdings ?? []}
                onSelectInstrument={(ticker, name) =>
                  setSelected({ ticker, name })
                }
              />
            )}
          </div>
        );
      })}

      {/* Slide‑in instrument detail panel */}
      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default GroupPortfolioView;
