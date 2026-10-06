import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { getGroupCurrencyContributions, getGroupPortfolio, getSleeves } from "../api";
import type { Account, CurrencyContribution, GroupPortfolio, SleeveList } from "../types";
import { translateInstrumentType } from "../lib/instrumentType";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { ReportingCurrencyNote } from "../components/ReportingCurrencyNote";
import { useConfig } from "../ConfigContext";
import { RelativeViewToggle } from "../components/RelativeViewToggle";
import ChartSkeleton from "../components/skeletons/ChartSkeleton";
import { useViewportWidth } from "../hooks/useViewportWidth";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { PieLabelRenderProps } from "recharts";

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

const INLINE_PIE_LABEL_MIN_WIDTH = 640;

const toFiniteNumber = (value: unknown): number => {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

const isInvalidNumericInput = (value: unknown): boolean => {
  const numeric = typeof value === "number" ? value : Number(value);
  return !Number.isFinite(numeric);
};

const isDevEnvironment = (): boolean => import.meta.env.MODE !== "production";

type AllocationView = "asset" | "sector" | "region" | "currency" | "sleeve";

const ALLOCATION_VIEWS: readonly AllocationView[] = ["asset", "sector", "region", "currency", "sleeve"];

const isAllocationView = (value: string | null): value is AllocationView =>
  value !== null && (ALLOCATION_VIEWS as readonly string[]).includes(value);

/** Backend label for holdings whose quote currency could not be resolved. */
const UNKNOWN_CURRENCY = "Unknown";

/** Pie slices for the quote-currency view, largest first; non-positive groups have no slice. */
const toCurrencySlices = (
  rows: CurrencyContribution[],
  unknownLabel: string,
): { name: string; value: number }[] =>
  rows
    .map((row) => ({
      name: row.quote_currency === UNKNOWN_CURRENCY ? unknownLabel : row.quote_currency,
      value: toFiniteNumber(row.market_value_gbp),
    }))
    .filter((slice) => slice.value > 0)
    .sort((a, b) => b.value - a.value);

/** Quote currencies with holdings that have no stored GBP rate, e.g. "JPY (2)". */
const missingFxSummary = (rows: CurrencyContribution[]): string =>
  rows
    .filter((row) => (row.unconverted_holdings?.length ?? 0) > 0)
    .map((row) => `${row.quote_currency} (${row.unconverted_holdings?.length})`)
    .join(", ");

/**
 * Quote-currency exposure for ``slug`` from the backend (#9686), which folds
 * GBX into GBP and resolves each holding's currency from its listing. Fetched
 * only once ``enabled`` (the view is open), and refetched after an error.
 * Covers the whole group: the endpoint has no per-account filter.
 */
function useGroupCurrencyExposure(slug: string, enabled: boolean) {
  const [rows, setRows] = useState<CurrencyContribution[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    setError(null);
  }, [slug]);

  useEffect(() => {
    if (!enabled || rows !== null) return;
    let cancelled = false;
    getGroupCurrencyContributions(slug)
      .then((result) => {
        if (cancelled) return;
        setRows(result);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, slug, rows]);

  return { rows, error };
}

/**
 * Each owner's sleeves and ticker tags (#9813), fetched once the sleeve view
 * is open. Tags are per owner, so a ticker can sit in different sleeves for
 * different owners in the same group.
 */
function useOwnerSleeves(owners: string[], enabled: boolean) {
  const [sleeves, setSleeves] = useState<Record<string, SleeveList> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ownerKey = owners.join(",");

  useEffect(() => {
    setSleeves(null);
    setError(null);
  }, [ownerKey]);

  useEffect(() => {
    if (!enabled || sleeves !== null || owners.length === 0) return;
    let cancelled = false;
    Promise.all(owners.map((owner) => getSleeves(owner).then((list) => [owner, list] as const)))
      .then((entries) => {
        if (!cancelled) setSleeves(Object.fromEntries(entries));
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
    // ownerKey stands in for owners, whose array identity changes every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ownerKey, sleeves]);

  return { sleeves, error };
}

/** The name of the sleeve ``ticker`` is tagged into for its owner; untagged holdings are in the core. */
const sleeveName = (list: SleeveList | undefined, ticker: string, coreLabel: string): string => {
  const sleeveId = list?.assignments[ticker.trim().toUpperCase()];
  const sleeve = sleeveId ? list?.sleeves.find((s) => s.id === sleeveId) : undefined;
  return sleeve && sleeve.id !== "core" ? sleeve.name : coreLabel;
};

export type AllocationChartsProps = {
  /** Portfolio group slug (defaults to "all"). */
  slug?: string;
};

export function AllocationCharts({ slug = "all" }: AllocationChartsProps) {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const resolvedSlug = searchParams.get("group") || slug;
  const requestedView = searchParams.get("view");
  const initialView: AllocationView = isAllocationView(requestedView) ? requestedView : "asset";
  const { relativeViewEnabled } = useConfig();
  const reporting = useReportingCurrency();
  const [view, setView] = useState<AllocationView>(initialView);
  const [sectorData, setSectorData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const [regionData, setRegionData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const [assetData, setAssetData] = useState<{ name: string; value: number }[]>(
    [],
  );
  const { rows: currencyRows, error: currencyError } = useGroupCurrencyExposure(
    resolvedSlug,
    view === "currency",
  );
  const [sleeveData, setSleeveData] = useState<{ name: string; value: number }[]>([]);
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const owners = [
    ...new Set(
      (portfolio?.accounts ?? []).map((acct) => acct.owner?.trim()).filter((o): o is string => !!o),
    ),
  ].sort();
  const { sleeves: ownerSleeves, error: sleeveError } = useOwnerSleeves(owners, view === "sleeve");
  const [selectedAccounts, setSelectedAccounts] = useState<string[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const allToggleRef = useRef<HTMLInputElement>(null);
  const showInlinePieLabels = useViewportWidth() >= INLINE_PIE_LABEL_MIN_WIDTH;
  const supportsResizeObserver =
    typeof window !== "undefined" && typeof window.ResizeObserver === "function";

  // helper to derive a stable key for each account
  const accountKey = (acct: Account, idx: number) =>
    `${acct.owner?.trim() || "unknown"}-${acct.account_type}-${idx}`;

  const toggleAccount = (key: string, allKeys: string[]) =>
    setSelectedAccounts((prev) => {
      if (prev === null) {
        return allKeys.filter((k) => k !== key);
      }
      return prev.includes(key)
        ? prev.filter((k) => k !== key)
        : [...prev, key];
    });

  useEffect(() => {
    setLoading(true);
    setError(null);
    getGroupPortfolio(resolvedSlug)
      .then((p: GroupPortfolio) => {
        setPortfolio(p);
        const owner = searchParams.get("owner");
        const account = searchParams.get("account");
        setSelectedAccounts(
          p.accounts
            .map((acct, idx) => ({ acct, key: accountKey(acct, idx) }))
            .filter(({ acct }) =>
              (!owner || acct.owner === owner) && (!account || acct.account_type === account),
            )
            .map(({ key }) => key),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [resolvedSlug, searchParams]);

  useEffect(() => {
    if (!portfolio) return;
    const allKeys = portfolio.accounts.map(accountKey);
    const activeKeys =
      selectedAccounts === null
        ? new Set(allKeys)
        : new Set(selectedAccounts);
    const activeAccounts = portfolio.accounts.filter((acct, idx) =>
      activeKeys.has(accountKey(acct, idx)),
    );

    const byType: Record<string, number> = {};
    const bySector: Record<string, number> = {};
    const byRegion: Record<string, number> = {};
    const bySleeve: Record<string, number> = {};
    const coreLabel = t("sleeves.core");

    for (const acct of activeAccounts) {
      for (const h of acct.holdings) {
        // API payloads may still include invalid numeric values at runtime even though TS types declare number.
        const originalMarketValue = h.market_value_gbp as unknown;
        const mv = toFiniteNumber(originalMarketValue);
        const originalInvalid = isInvalidNumericInput(originalMarketValue);
        const dropReason = originalInvalid
          ? "invalid-numeric-input"
          : mv <= 0
            ? "non-positive-market-value"
            : null;
        // Visualization safeguard only: exclude invalid numeric input and non-positive values.
        // Zero creates no drawable slice and negatives typically represent short/invalid values; this does not fix upstream data quality.
        if (dropReason) {
          if (isDevEnvironment()) {
            console.warn("Dropped invalid holding value", {
              ticker: h.ticker,
              originalValue: originalMarketValue,
              coercedValue: mv,
              originalInvalid,
              dropReason,
            });
          }
          continue;
        }
        const typeName = translateInstrumentType(t, h.instrument_type);
        byType[typeName] = (byType[typeName] || 0) + mv;
        const sector = h.sector || t("common.other");
        bySector[sector] = (bySector[sector] || 0) + mv;
        const region = h.region || t("common.other");
        byRegion[region] = (byRegion[region] || 0) + mv;
        const sleeve = sleeveName(ownerSleeves?.[acct.owner?.trim() ?? ""], h.ticker, coreLabel);
        bySleeve[sleeve] = (bySleeve[sleeve] || 0) + mv;
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
    setSleeveData(
      Object.entries(bySleeve)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value),
    );
  }, [portfolio, selectedAccounts, ownerSleeves, t]);

  useEffect(() => {
    if (!portfolio) return;
    const total = portfolio.accounts.length;
    const selectedCount =
      selectedAccounts === null ? total : selectedAccounts.length;
    if (allToggleRef.current) {
      allToggleRef.current.indeterminate =
        selectedCount > 0 && selectedCount < total;
    }
  }, [portfolio, selectedAccounts]);

  if (loading && !portfolio) {
    return (
      <div className="container mx-auto p-4">
        <ChartSkeleton height={400} label={t("app.loading")} />
      </div>
    );
  }

  const currencyData = toCurrencySlices(
    currencyRows ?? [],
    t("allocation.unknownCurrency", { defaultValue: "Unknown currency" }),
  );
  const chartDataByView: Record<AllocationView, { name: string; value: number }[]> = {
    asset: assetData,
    sector: sectorData,
    region: regionData,
    currency: currencyData,
    // Until every owner's tags have loaded, a sleeve chart would show everything as core.
    sleeve: ownerSleeves ? sleeveData : [],
  };
  const chartData = chartDataByView[view];
  const isCurrencyView = view === "currency";
  const missingFx = missingFxSummary(currencyRows ?? []);

  const total = chartData.reduce((sum, d) => sum + d.value, 0);
  const allKeys = portfolio?.accounts.map((acct, idx) => accountKey(acct, idx)) ?? [];
  const selectedCount =
    selectedAccounts === null ? allKeys.length : selectedAccounts.length;
  const allSelected =
    !!portfolio && selectedCount === allKeys.length && selectedCount > 0;

  const handleToggleAll = () => {
    if (!portfolio) return;
    setSelectedAccounts((prev) => {
      if (prev === null) {
        return [];
      }
      return prev.length === allKeys.length ? [] : [...allKeys];
    });
  };

  return (
    <div className="container mx-auto p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl md:text-4xl">
          {t("app.modes.allocation", { defaultValue: "Allocation" })}
        </h1>
        <RelativeViewToggle />
      </div>
      <p className="mb-4 text-sm text-gray-600">
        {t("allocation.allocationDescription")}{" "}
        <Link
          className="text-blue-600 underline"
          to={`/?${new URLSearchParams({ group: resolvedSlug }).toString()}`}
        >
          {t("allocation.viewContribution")}
        </Link>
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        <button onClick={() => setView("asset")} disabled={view === "asset"}>
          {t("allocation.instrumentTypes", { defaultValue: "Instrument Types" })}
        </button>
        <button onClick={() => setView("sector")} disabled={view === "sector"}>
          {t("allocation.sector")}
        </button>
        <button onClick={() => setView("region")} disabled={view === "region"}>
          {t("allocation.region")}
        </button>
        <button onClick={() => setView("currency")} disabled={isCurrencyView}>
          {t("allocation.currency", { defaultValue: "Currencies" })}
        </button>
        <button onClick={() => setView("sleeve")} disabled={view === "sleeve"}>
          {t("allocation.sleeve")}
        </button>
      </div>
      {isCurrencyView && (
        <p className="mb-4 text-sm text-gray-600" data-testid="currency-exposure-note">
          {t("allocation.currencyNote")}
        </p>
      )}
      {view === "sleeve" && (
        <p className="mb-4 text-sm text-gray-600" data-testid="sleeve-note">
          {t("allocation.sleeveNote")}
        </p>
      )}
      {portfolio && !isCurrencyView && (
        <div className="mb-4 flex flex-wrap gap-4">
          <label className="flex items-center gap-1 font-semibold">
            <input
              ref={allToggleRef}
              type="checkbox"
              checked={allSelected}
              onChange={handleToggleAll}
            />
            {t("common.all", { defaultValue: "All" })}
          </label>
          {portfolio.accounts.map((acct, idx) => {
            const key = accountKey(acct, idx);
            const isChecked =
              selectedAccounts === null
                ? true
                : selectedAccounts.includes(key);
            return (
              <label key={key} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggleAccount(key, allKeys)}
                />
                {`${acct.owner ?? "—"} - ${acct.account_type}`}
              </label>
            );
          })}
        </div>
      )}
      {error && <p className="text-red-500">{error}</p>}
      {isCurrencyView && currencyError && <p className="text-red-500">{currencyError}</p>}
      {view === "sleeve" && sleeveError && <p className="text-red-500">{sleeveError}</p>}
      {isCurrencyView && missingFx && (
        <p className="mb-4 text-sm text-amber-700" role="status" data-testid="currency-missing-fx">
          {t("allocation.currencyMissingFx", { currencies: missingFx })}
        </p>
      )}
      <div style={{ width: "100%", height: 400 }}>
        {supportsResizeObserver ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius="80%"
                // "percent" may be undefined for empty datasets; default it to 0
                label={showInlinePieLabels && ((props) => {
                  const { name, value, percent: slicePercent } = props as PieLabelRenderProps;
                  const labelName = typeof name === "string" ? name : name != null ? String(name) : "";
                  const percentValue = (slicePercent ?? 0) * 100;
                  const rawValue =
                    typeof value === "number"
                      ? value
                      : typeof value === "string"
                        ? Number(value)
                        : 0;
                  const numericValue = Number.isFinite(rawValue) ? rawValue : 0;
                  return relativeViewEnabled
                    ? `${labelName}: ${percentValue.toFixed(2)}%`
                    : `${labelName}: ${reporting.format(numericValue)} (${percentValue.toFixed(2)}%)`;
                })}
              >
                {chartData.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(v, _n, item) =>
                  relativeViewEnabled
                    ? `${
                        total
                          ? (((item as any)?.payload?.value / total) * 100).toFixed(2)
                          : "0.00"
                      }%`
                    : reporting.format(v as number | undefined)
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
                    : `${value}: ${reporting.format(entry?.payload?.value)}`
                }
              />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <div
            data-testid="allocation-chart-fallback"
            className="flex h-full items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-sm text-gray-600"
          >
            {t("allocation.chartsUnavailable", {
              defaultValue: "Charts are unavailable in this environment.",
            })}
          </div>
        )}
      </div>
      {!relativeViewEnabled && <ReportingCurrencyNote reporting={reporting} />}
    </div>
  );
}

export default AllocationCharts;
