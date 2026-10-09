import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import {
  getGroupCurrencyContributions,
  getGroupLookThrough,
  getGroupPortfolio,
  getOwnerCurrencyContributions,
  getOwnerLookThrough,
  getSleeves,
} from "../api";
import type {
  CurrencyContribution,
  GroupPortfolio,
  LookThroughBucket,
  LookThroughExposure,
  OwnerSummary,
  SleeveList,
} from "../types";
import { LookThroughCoverageNote, LookThroughHoldingsTable } from "../components/LookThrough";
import { translateInstrumentType } from "../lib/instrumentType";
import { isCashInstrument } from "../lib/instruments";
import { accountTypeLabel } from "../utils/accountTypes";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { ReportingCurrencyNote } from "../components/ReportingCurrencyNote";
import { useConfig } from "../ConfigContext";
import { RelativeViewToggle } from "../components/RelativeViewToggle";
import { OwnerAccountTabs } from "../components/OwnerAccountTabs";
import { buildOwnerTabs } from "../lib/ownerTabs";
import { createOwnerDisplayLookup, getOwnerDisplayName } from "../utils/owners";
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
import { renderPieLabelLine, withSmallSliceLabelsHidden } from "../lib/pieLabels";

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

type LookThroughView = "lt-country" | "lt-sector" | "lt-holdings";
type AllocationView = "asset" | "sector" | "region" | "currency" | "sleeve" | LookThroughView;

const LOOK_THROUGH_VIEWS: readonly AllocationView[] = ["lt-country", "lt-sector", "lt-holdings"];
const ALLOCATION_VIEWS: readonly AllocationView[] = [
  "asset",
  "sector",
  "region",
  "currency",
  "sleeve",
  ...LOOK_THROUGH_VIEWS,
];

/** Look-through pie slices beyond this many are folded into one "Other" slice. */
const MAX_LOOK_THROUGH_SLICES = 12;

/** Views built from the portfolio's own holdings, which can show those holdings in an outer ring. */
type HoldingView = "asset" | "sector" | "region" | "sleeve";
const HOLDING_VIEWS: readonly HoldingView[] = ["asset", "sector", "region", "sleeve"];

const isHoldingView = (value: AllocationView): value is HoldingView =>
  (HOLDING_VIEWS as readonly string[]).includes(value);

type Slice = { name: string; value: number };
/** Holding ticker -> display name and value, within one allocation group. */
type GroupHoldings = Record<string, Slice>;
/** Allocation group (e.g. "ETF") -> the holdings making it up. */
type Breakdown = Record<string, GroupHoldings>;

const emptyBreakdowns = (): Record<HoldingView, Breakdown> => ({
  asset: {},
  sector: {},
  region: {},
  sleeve: {},
});

const addToBreakdown = (
  breakdown: Breakdown,
  group: string,
  ticker: string,
  name: string,
  mv: number,
) => {
  const holdings = (breakdown[group] ??= {});
  const entry = (holdings[ticker] ??= { name, value: 0 });
  entry.value += mv;
};

const byValueDesc = (a: Slice, b: Slice) => b.value - a.value;

/** One slice per group, largest first. */
const groupSlices = (breakdown: Breakdown): Slice[] =>
  Object.entries(breakdown)
    .map(([name, holdings]) => ({
      name,
      value: Object.values(holdings).reduce((sum, h) => sum + h.value, 0),
    }))
    .sort(byValueDesc);

/** A holding slice in the outer ring, coloured by the group it belongs to. */
type HoldingSlice = Slice & { group: string; groupIndex: number };

/**
 * Outer-ring slices: each group's holdings, largest first, in the same order
 * as ``groups`` so every holding sits directly outside its group's slice.
 */
const holdingSlices = (breakdown: Breakdown, groups: Slice[]): HoldingSlice[] =>
  groups.flatMap((group, groupIndex) =>
    Object.values(breakdown[group.name] ?? {})
      .sort(byValueDesc)
      .map((h) => ({ ...h, group: group.name, groupIndex })),
  );

/** Outer-ring labels longer than this are cut short; the tooltip shows the full name. */
const MAX_HOLDING_LABEL_LENGTH = 24;

const shortLabel = (name: string): string =>
  name.length > MAX_HOLDING_LABEL_LENGTH
    ? `${name.slice(0, MAX_HOLDING_LABEL_LENGTH - 1)}…`
    : name;

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
 * Quote-currency exposure from the backend (#9686), which folds GBX into GBP
 * and resolves each holding's currency from its listing: for ``owner`` when
 * one is selected, otherwise for the whole ``slug`` group. Fetched only once
 * ``enabled`` (the view is open), and refetched after an error. The endpoints
 * have no per-account filter, so an account selection still shows the owner.
 */
function useCurrencyExposure(slug: string, owner: string | null, enabled: boolean) {
  const [rows, setRows] = useState<CurrencyContribution[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    setError(null);
  }, [slug, owner]);

  useEffect(() => {
    if (!enabled || rows !== null) return;
    let cancelled = false;
    (owner ? getOwnerCurrencyContributions(owner) : getGroupCurrencyContributions(slug))
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
  }, [enabled, slug, owner, rows]);

  return { rows, error };
}

/** Pie slices for a look-through breakdown, largest first, the tail folded into ``otherLabel``. */
const toLookThroughSlices = (
  rows: LookThroughBucket[],
  otherLabel: string,
): { name: string; value: number }[] => {
  const slices = rows
    .map((row) => ({ name: row.label, value: toFiniteNumber(row.value_gbp) }))
    .filter((slice) => slice.value > 0)
    .sort((a, b) => b.value - a.value);
  if (slices.length <= MAX_LOOK_THROUGH_SLICES) return slices;
  const head = slices.slice(0, MAX_LOOK_THROUGH_SLICES - 1);
  const rest = slices.slice(MAX_LOOK_THROUGH_SLICES - 1).reduce((sum, s) => sum + s.value, 0);
  return [...head, { name: otherLabel, value: rest }];
};

/**
 * Look-through exposure (#9974): funds split into their underlying countries,
 * sectors and holdings, combined with direct shares. Like the currency view it
 * covers ``owner`` when one is selected, otherwise the whole ``slug`` group,
 * and is fetched only once ``enabled`` (a look-through view is open).
 */
function useLookThrough(slug: string, owner: string | null, enabled: boolean) {
  const [data, setData] = useState<LookThroughExposure | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
  }, [slug, owner]);

  useEffect(() => {
    if (!enabled || data !== null) return;
    let cancelled = false;
    (owner ? getOwnerLookThrough(owner) : getGroupLookThrough(slug))
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, slug, owner, data]);

  return { data, error };
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
  /** Owner summaries, used for owner tab display names. */
  owners?: OwnerSummary[];
};

export function AllocationCharts({ slug = "all", owners }: AllocationChartsProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const resolvedSlug = searchParams.get("group") || slug;
  const requestedView = searchParams.get("view");
  const initialView: AllocationView = isAllocationView(requestedView) ? requestedView : "asset";
  const { relativeViewEnabled } = useConfig();
  const reporting = useReportingCurrency();
  const [view, setView] = useState<AllocationView>(initialView);
  const [breakdowns, setBreakdowns] = useState<Record<HoldingView, Breakdown>>(emptyBreakdowns);
  const [showHoldings, setShowHoldings] = useState(false);
  const activeOwner = searchParams.get("owner") || null;
  const activeAccountType = activeOwner ? searchParams.get("account") || null : null;
  const { rows: currencyRows, error: currencyError } = useCurrencyExposure(
    resolvedSlug,
    activeOwner,
    view === "currency",
  );
  const isLookThroughView = LOOK_THROUGH_VIEWS.includes(view);
  const { data: lookThrough, error: lookThroughError } = useLookThrough(
    resolvedSlug,
    activeOwner,
    isLookThroughView,
  );
  const [portfolio, setPortfolio] = useState<GroupPortfolio | null>(null);
  const groupOwners = [
    ...new Set(
      (portfolio?.accounts ?? []).map((acct) => acct.owner?.trim()).filter((o): o is string => !!o),
    ),
  ].sort();
  const { sleeves: ownerSleeves, error: sleeveError } = useOwnerSleeves(groupOwners, view === "sleeve");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const showInlinePieLabels = useViewportWidth() >= INLINE_PIE_LABEL_MIN_WIDTH;
  const supportsResizeObserver =
    typeof window !== "undefined" && typeof window.ResizeObserver === "function";

  const ownerLookup = useMemo(() => createOwnerDisplayLookup(owners ?? []), [owners]);
  const ownerTabs = useMemo(
    () => buildOwnerTabs(portfolio?.accounts, ownerLookup),
    [portfolio, ownerLookup],
  );

  /** Same ``?owner=&account=`` scope as the portfolio overview; changing owner clears account. */
  const setScope = useCallback(
    (owner: string | null, account: string | null, options?: { replace?: boolean }) => {
      setSearchParams((prev) => {
        const params = new URLSearchParams(prev);
        if (owner) params.set("owner", owner);
        else params.delete("owner");
        if (owner && account) params.set("account", account);
        else params.delete("account");
        return params;
      }, options);
    },
    [setSearchParams],
  );

  useEffect(() => {
    setLoading(true);
    setError(null);
    getGroupPortfolio(resolvedSlug)
      .then((p: GroupPortfolio) => setPortfolio(p))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [resolvedSlug]);

  // Drop an owner/account the loaded group doesn't have, as the overview does.
  useEffect(() => {
    if (!portfolio || ownerTabs.length === 0 || !activeOwner) return;
    const tab = ownerTabs.find((entry) => entry.value === activeOwner);
    if (!tab) setScope(null, null, { replace: true });
    else if (activeAccountType && !tab.accountTypes.includes(activeAccountType))
      setScope(activeOwner, null, { replace: true });
  }, [portfolio, ownerTabs, activeOwner, activeAccountType, setScope]);

  useEffect(() => {
    if (!portfolio) return;
    const activeAccounts = portfolio.accounts.filter(
      (acct) =>
        (!activeOwner || acct.owner === activeOwner) &&
        (!activeAccountType || acct.account_type === activeAccountType),
    );

    const next = emptyBreakdowns();
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
        const groups: Record<HoldingView, string> = {
          asset: translateInstrumentType(t, h.instrument_type),
          sector: h.sector || t("common.other"),
          region: h.region || t("common.other"),
          sleeve: sleeveName(ownerSleeves?.[acct.owner?.trim() ?? ""], h.ticker, coreLabel),
        };
        const name = h.name || h.ticker;
        // Every account's cash shares a ticker (e.g. CASH.GBP), so keep each
        // owner's account apart rather than folding all cash into one slice.
        const isCash = isCashInstrument(h);
        const key = isCash ? `${acct.owner}|${acct.account_type}|${h.ticker}` : h.ticker;
        const label = isCash
          ? t("allocation.accountCash", {
              owner: getOwnerDisplayName(ownerLookup, acct.owner, acct.owner),
              account: accountTypeLabel(acct.account_type),
              name,
            })
          : name;
        for (const dimension of HOLDING_VIEWS) {
          addToBreakdown(next[dimension], groups[dimension], key, label, mv);
        }
      }
    }

    setBreakdowns(next);
  }, [portfolio, activeOwner, activeAccountType, ownerSleeves, ownerLookup, t]);

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
    asset: groupSlices(breakdowns.asset),
    sector: groupSlices(breakdowns.sector),
    region: groupSlices(breakdowns.region),
    currency: currencyData,
    // Until every owner's tags have loaded, a sleeve chart would show everything as core.
    sleeve: ownerSleeves ? groupSlices(breakdowns.sleeve) : [],
    "lt-country": toLookThroughSlices(lookThrough?.countries ?? [], t("common.other")),
    "lt-sector": toLookThroughSlices(lookThrough?.sectors ?? [], t("common.other")),
    "lt-holdings": [],
  };
  const chartData = chartDataByView[view];
  const canShowHoldings = isHoldingView(view);
  const outerRing =
    isHoldingView(view) && showHoldings ? holdingSlices(breakdowns[view], chartData) : null;
  const isCurrencyView = view === "currency";
  const missingFx = missingFxSummary(currencyRows ?? []);

  const total = chartData.reduce((sum, d) => sum + d.value, 0);
  /** A slice's share of the chart total, e.g. "12.34%". */
  const sharePct = (value: unknown): string =>
    `${total ? ((toFiniteNumber(value) / total) * 100).toFixed(2) : "0.00"}%`;
  /** Inline slice label: name, value (unless relative view) and share of the whole chart. */
  const formatSliceLabel = (props: PieLabelRenderProps): string => {
    const { name, value, percent: slicePercent } = props;
    const labelName = typeof name === "string" ? name : name != null ? String(name) : "";
    // "percent" may be undefined for empty datasets; default it to 0
    const percentValue = (slicePercent ?? 0) * 100;
    const rawValue =
      typeof value === "number" ? value : typeof value === "string" ? Number(value) : 0;
    const numericValue = Number.isFinite(rawValue) ? rawValue : 0;
    return relativeViewEnabled
      ? `${labelName}: ${percentValue.toFixed(2)}%`
      : `${labelName}: ${reporting.format(numericValue)} (${percentValue.toFixed(2)}%)`;
  };
  const contributionParams = new URLSearchParams({ group: resolvedSlug });
  if (activeOwner) contributionParams.set("owner", activeOwner);
  if (activeAccountType) contributionParams.set("account", activeAccountType);

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
          to={`/?${contributionParams.toString()}`}
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
        <button onClick={() => setView("lt-country")} disabled={view === "lt-country"}>
          {t("lookThrough.countriesView")}
        </button>
        <button onClick={() => setView("lt-sector")} disabled={view === "lt-sector"}>
          {t("lookThrough.sectorsView")}
        </button>
        <button onClick={() => setView("lt-holdings")} disabled={view === "lt-holdings"}>
          {t("lookThrough.holdingsView")}
        </button>
      </div>
      {canShowHoldings && (
        <label className="mb-4 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showHoldings}
            onChange={(e) => setShowHoldings(e.target.checked)}
            data-testid="show-holdings-toggle"
          />
          {t("allocation.showHoldings")}
        </label>
      )}
      {isLookThroughView && (
        <p className="mb-2 text-sm text-gray-600" data-testid="look-through-note">
          {t("lookThrough.note")}
        </p>
      )}
      {isLookThroughView && lookThrough && (
        <LookThroughCoverageNote
          coverage={lookThrough.coverage}
          format={(v) => reporting.format(v)}
          totalValue={lookThrough.total_value_gbp}
        />
      )}
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
      {portfolio && (
        <OwnerAccountTabs
          ownerTabs={ownerTabs}
          activeOwner={activeOwner}
          activeAccountType={activeAccountType}
          onOwnerChange={(owner) => setScope(owner, null)}
          onAccountTypeChange={(type) => setScope(activeOwner, type)}
        />
      )}
      {error && <p className="text-red-500">{error}</p>}
      {isCurrencyView && currencyError && <p className="text-red-500">{currencyError}</p>}
      {view === "sleeve" && sleeveError && <p className="text-red-500">{sleeveError}</p>}
      {isLookThroughView && lookThroughError && <p className="text-red-500">{lookThroughError}</p>}
      {isCurrencyView && missingFx && (
        <p className="mb-4 text-sm text-amber-700" role="status" data-testid="currency-missing-fx">
          {t("allocation.currencyMissingFx", { currencies: missingFx })}
        </p>
      )}
      {view === "lt-holdings" ? (
        lookThrough ? (
          <LookThroughHoldingsTable
            holdings={lookThrough.holdings}
            format={(v) => reporting.format(v)}
            totalValue={lookThrough.total_value_gbp}
          />
        ) : (
          !lookThroughError && <ChartSkeleton height={400} label={t("app.loading")} />
        )
      ) : (
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
                  // With the holdings ring on, the groups sit inside it and the legend names them.
                  outerRadius={outerRing ? "52%" : "80%"}
                  labelLine={showInlinePieLabels && !outerRing && renderPieLabelLine}
                  label={
                    showInlinePieLabels && !outerRing && withSmallSliceLabelsHidden(formatSliceLabel)
                  }
                >
                  {chartData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                {outerRing && (
                  <Pie
                    data={outerRing}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius="54%"
                    outerRadius="80%"
                    legendType="none"
                    labelLine={showInlinePieLabels && renderPieLabelLine}
                    label={
                      showInlinePieLabels &&
                      withSmallSliceLabelsHidden((props) =>
                        formatSliceLabel({ ...props, name: shortLabel(String(props.name ?? "")) }),
                      )
                    }
                  >
                    {outerRing.map((slice, index) => (
                      <Cell
                        key={`holding-${index}`}
                        fill={COLORS[slice.groupIndex % COLORS.length]}
                        // Alternate shades so neighbouring holdings in one group stay distinguishable.
                        fillOpacity={index % 2 === 0 ? 0.85 : 0.6}
                      />
                    ))}
                  </Pie>
                )}
                <Tooltip
                  formatter={(v, _n, item) => {
                    const share = sharePct((item as any)?.payload?.value);
                    return relativeViewEnabled
                      ? share
                      : `${reporting.format(v as number | undefined)} (${share})`;
                  }}
                />
                <Legend
                  formatter={(value: string, entry: any) => {
                    const share = sharePct(entry?.payload?.value);
                    return relativeViewEnabled
                      ? `${value}: ${share}`
                      : `${value}: ${reporting.format(entry?.payload?.value)} (${share})`;
                  }}
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
      )}
      {!relativeViewEnabled && <ReportingCurrencyNote reporting={reporting} />}
    </div>
  );
}

export default AllocationCharts;
