import {
  Fragment,
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useMemo,
  type MouseEvent,
} from "react";
import { useTranslation } from "react-i18next";
import type { Holding } from "../types";
import { percent } from "../lib/money";
import { instrumentTooltip, translateInstrumentType } from "../lib/instrumentType";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";
import { useConfig } from "../ConfigContext";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { isSupportedFx } from "../lib/fx";
import { formatDateISO } from "../lib/date";
import {
  COST_BASIS_BOOK_SUSPECT,
  isCostBasisUnreliable,
} from "../lib/costBasis";
import {
  FX_RATE_SOURCE_MISSING,
  isFxRateFlagged,
} from "../lib/fxRateSource";
import {
  HoldingsFilterControls,
  type SparkRange,
} from "./HoldingsFilterControls";
import FilterBar, { useFilterReducer, type FilterState } from "./FilterBar";
import EmptyState from "./EmptyState";
import { useNavigate } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import Sparkline from "./Sparkline";
import { getGrowthStage } from "../utils/growthStage";
import { preloadInstrumentHistory } from "../hooks/useInstrumentHistory";
import type { InstrumentGroupDefinition } from "../types";
import type { RollupRow } from "../lib/rollupAdapter";
import {
  COLUMN_PRESETS,
  COLUMN_VISIBILITY_STORAGE_KEY,
  RELATIVE_VIEW_HIDDEN,
  TRAILING_COLUMNS,
  loadColumnVisibility,
  matchingPreset,
  type ColumnKey,
  type ColumnPreset,
  type ColumnVisibility,
} from "../lib/holdingsColumns";
import { getVirtualSpacerHeights } from "./instrumentTable/virtualPadding";
import {
  buildCategoryLookup,
  calculateGroupTotals,
  createGroups,
  sanitizeGroupKey,
} from "./instrumentTable/utils";
import type {
  GroupedRows,
  GroupingMode,
  RowWithCost,
} from "./instrumentTable/types";

const VIEW_PRESET_STORAGE_KEY = "holdingsTableViewPreset";
const ESTIMATED_ROW_HEIGHT = 32;
// Ticker and name are rendered in every row. Everything else is gated on
// showAccount / relative view / visibleColumns / forward ranges.
const ALWAYS_VISIBLE_COLUMN_COUNT = 2;

// Every column HoldingsTable can sort on. sortBy() only accepts these, so a new
// sortable column fails to compile until it gets a GROUP_SORT_KEYS entry.
type HoldingsSortKey =
  | "ticker"
  | "name"
  | "sector"
  | "gain"
  | "gain_pct"
  | "total_return_gbp"
  | "income_gbp"
  | "cost"
  | "forward_7d_change_pct"
  | "forward_30d_change_pct"
  | "weight_pct"
  | "days_held";

// HoldingsTable sorts on its own row keys; createGroups orders groups by
// RowWithCost keys. Translate so groups sort by their totals (#8529). Weight %
// is market value / portfolio total, so group weight order == market value order.
// null = no group total exists, so groups keep first-appearance order.
const GROUP_SORT_KEYS: Record<HoldingsSortKey, keyof RowWithCost | null> = {
  ticker: "ticker",
  name: "name",
  sector: "sector",
  gain: "gain_gbp",
  gain_pct: "gain_pct",
  total_return_gbp: null,
  income_gbp: null,
  cost: "cost",
  forward_7d_change_pct: "change_7d_pct",
  forward_30d_change_pct: "change_30d_pct",
  weight_pct: "market_value_gbp",
  days_held: null,
};

type IndexedGroupRow = RowWithCost & { __holdingsIndex: number };

type HoldingsTableRow = Holding & {
  source_account?: string;
  row_key?: string;
  grouping?: string | null;
  change_7d_pct?: number | null;
  change_30d_pct?: number | null;
};

type Props = {
  holdings: HoldingsTableRow[] | RollupRow[];
  // Rollup rows have no per-lot fields, so lot-only filters and sorts are suppressed (§3 rule 2).
  rollupMode?: boolean;
  showAccount?: boolean;
  onSelectInstrument?: (
    ticker: string,
    name: string,
    instrumentType?: string | null,
  ) => void;
  selectedTicker?: string;
  showForward7d?: boolean;
  showForward30d?: boolean;
  onAddPosition?: () => void;
  groupingMode?: GroupingMode;
  categoryDefinitions?: InstrumentGroupDefinition[];
};


export function HoldingsTable({
  holdings,
  rollupMode = false,
  showAccount = false,
  onSelectInstrument,
  selectedTicker,
  showForward7d = false,
  showForward30d = false,
  onAddPosition,
  groupingMode = "flat",
  categoryDefinitions = [],
}: Props) {
  // RollupRow is the adapter's deliberately presentation-neutral shape. Its
  // nullable lot-only fields are rendered the same way as absent Holding fields.
  const holdingRows = holdings as HoldingsTableRow[];
  const { t } = useTranslation();
  const { relativeViewEnabled, familyMvpEnabled } = useConfig();
  const reporting = useReportingCurrency();
  let navigate: (path: string) => void = () => {};
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    navigate = useNavigate();
  } catch {
    // Intentional: component may be rendered outside a Router in tests/storybook.
    // useNavigate() is only used for the EmptyState screener shortcut.
  }

  const viewPresets = useMemo(() => {
    const instrumentTypes = new Map<string, string>();
    holdingRows.forEach(({ instrument_type: instrumentType }) => {
      const trimmedType = instrumentType?.trim();
      if (trimmedType) {
        instrumentTypes.set(trimmedType.toLocaleLowerCase(), trimmedType);
      }
    });

    return [
      { label: t("holdingsTable.viewPresets.all"), value: "" },
      ...Array.from(instrumentTypes.values()).map((instrumentType) => ({
        label: translateInstrumentType(t, instrumentType),
        value: instrumentType,
      })),
    ];
  }, [holdingRows, t]);

  const [filters, dispatchFilters] = useFilterReducer();

  const [viewPreset, setViewPreset] = useState(() =>
    typeof window === "undefined"
      ? ""
      : localStorage.getItem(VIEW_PRESET_STORAGE_KEY) || ""
  );

  const [visibleColumns, setVisibleColumns] =
    useState<ColumnVisibility>(loadColumnVisibility);
  const activeColumnPreset = matchingPreset(visibleColumns);
  const show = (key: ColumnKey) =>
    visibleColumns[key] && !(relativeViewEnabled && RELATIVE_VIEW_HIDDEN.has(key));
  const trailingColumnCount = TRAILING_COLUMNS.filter(show).length;

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      localStorage.setItem(
        COLUMN_VISIBILITY_STORAGE_KEY,
        JSON.stringify(visibleColumns),
      );
    } catch (error) {
      console.warn("Could not save holdings column preferences", error);
    }
  }, [visibleColumns]);

  const [sparkRange, setSparkRange] = useState<SparkRange>(30);

  const [missingHistoryTickers, setMissingHistoryTickers] = useState<string[]>(
    [],
  );

  useEffect(() => {
    if (viewPreset && !viewPresets.some(({ value }) => value === viewPreset)) {
      setViewPreset("");
    }
  }, [viewPreset, viewPresets]);

  useEffect(() => {
    const tickers = Array.from(new Set(holdingRows.map((h) => h.ticker)));
    if (tickers.length) {
      preloadInstrumentHistory(tickers, sparkRange)
        .then(setMissingHistoryTickers)
        .catch(() => {});
    } else {
      setMissingHistoryTickers([]);
    }
  }, [holdingRows, sparkRange]);

  const toggleColumn = (key: ColumnKey) => {
    setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleFilterChange = (key: keyof FilterState, value: string) => {
    dispatchFilters({ type: "set", key, value });
  };

  const clearFilters = () => {
    dispatchFilters({ type: "clearAll" });
    setViewPreset("");
  };

  const getPerformanceClass = (value: number | null | undefined): string => {
    if (typeof value !== "number" || !Number.isFinite(value) || value === 0) {
      return "text-gray";
    }

    return value > 0 ? "text-positive" : "text-negative";
  };

  // Gain is shown as N/A (not a figure) whenever it is null: no positive cost
  // (#8471), a guessed cost ("unknown", #7220) or an implausible booked cost
  // ("book_suspect", #8472). The tooltip says which.
  const gainWithheldTitle = (source: string | null | undefined): string =>
    source === COST_BASIS_BOOK_SUSPECT
      ? t("holdingsTable.bookCostSuspect")
      : t("holdingsTable.gainNotAvailable");

  // An approximate (fallback) or absent (missing) FX rate (#9664, #9730).
  const fxRateTitle = (source: string | null | undefined): string =>
    source === FX_RATE_SOURCE_MISSING
      ? t("holdingsTable.fxRateMissing")
      : t("holdingsTable.fxRateFallback");

  // Says whether income is estimated and gives the trailing yield (#10395).
  const incomeTitle = (h: Holding): string | undefined => {
    if (h.income_gbp === undefined) return undefined;
    if (h.income_gbp === null) return t("holdingsTable.totalReturnNoTransactions");
    const parts = [];
    if (h.income_estimated) parts.push(t("holdingsTable.incomeEstimated"));
    if (h.yield_pct != null) parts.push(t("holdingsTable.incomeYield", { yield: percent(h.yield_pct, 1) }));
    return parts.join(" · ") || undefined;
  };

  // Breaks the total return into its parts (#9038); cash rows carry none.
  const totalReturnTitle = (h: Holding): string | undefined => {
    if (h.total_return_gbp === undefined) return undefined;
    if (h.income_gbp == null) return t("holdingsTable.totalReturnNoTransactions");
    return t("holdingsTable.totalReturnBreakdown", {
      income: reporting.format(h.income_gbp),
      realised:
        h.realised_gain_gbp == null
          ? t("holdingsTable.notApplicable")
          : reporting.format(h.realised_gain_gbp),
    });
  };


  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(VIEW_PRESET_STORAGE_KEY, viewPreset);
    }
    dispatchFilters({ type: "set", key: "instrument_type", value: viewPreset });
    // dispatchFilters is stable (useReducer dispatch), including it satisfies exhaustive-deps without risk
  }, [viewPreset, dispatchFilters]);

  // derive cost/market/gain/gain_pct
  const computed = holdingRows.map((h) => {
    // effective_cost_basis_gbp is the canonical cost used for gain: the
    // backend sets it equal to cost_basis_gbp for booked lots and to the
    // derived cost otherwise. Preferring it keeps flat rows unchanged and
    // makes rollup rows correct even when a ticker mixes booked and derived
    // lots (cost_basis_gbp alone would understate the total).
    const cost =
      (h.effective_cost_basis_gbp ?? 0) > 0
        ? h.effective_cost_basis_gbp ?? 0
        : h.cost_basis_gbp ?? 0;

    const market = h.market_value_gbp ?? 0;

    // No positive cost, a last-resort guessed cost ("unknown", #7220) or an
    // implausible booked cost ("book_suspect", #8472): the gain is unknown, so
    // keep it null rather than inventing 0%, a gain equal to the market value
    // (#8471), or re-deriving the absurd figure the backend withheld.
    if (cost <= 0 || isCostBasisUnreliable(h.cost_basis_source)) {
      return { ...h, cost, market, gain: null, gain_pct: null };
    }

    const gain =
      h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
        ? h.gain_gbp
        : market - cost;

    const gain_pct =
      h.gain_pct !== undefined && h.gain_pct !== null
        ? h.gain_pct
        : (gain / cost) * 100;

    return { ...h, cost, market, gain, gain_pct };
  });

  const totalMarket = computed.reduce((sum, h) => sum + (h.market ?? 0), 0);
  const rows = computed.map((h) => ({
    ...h,
    // Blank, not null, so the string sort never compares a string with null.
    // Sector grouping already treats a blank sector as unknown.
    sector: h.sector?.trim() ?? "",
    weight_pct: totalMarket ? ((h.market ?? 0) / totalMarket) * 100 : 0,
  }));

  // apply filters
  const filtered = rows.filter((h) => {
    if (filters.ticker && !h.ticker.toLowerCase().includes(filters.ticker.toLowerCase())) return false;
    if (filters.name && !(h.name ?? "").toLowerCase().includes(filters.name.toLowerCase())) return false;
    if (filters.instrument_type && !(h.instrument_type ?? "").toLowerCase().includes(filters.instrument_type.toLowerCase())) return false;

    if (filters.units) {
      const minUnits = parseFloat(filters.units);
      if (!Number.isNaN(minUnits) && (h.units ?? 0) < minUnits) return false;
    }
    if (filters.gain_pct) {
      const minGain = parseFloat(filters.gain_pct);
      // An unknown gain is neither above nor below the threshold (#8471).
      if (!Number.isNaN(minGain) && (h.gain_pct == null || h.gain_pct < minGain)) return false;
    }
    if (!rollupMode && filters.sell_eligible) {
      // sell_eligible is null when the acquisition date is unknown (#7220):
      // that is neither "eligible" nor "not eligible", so it must not match
      // either filter option. `!!null === false` previously coerced every
      // unknown holding into matching the "No" filter, which reported
      // unknown holdings as a confident "not eligible" -- exactly the
      // fabricated-certainty bug this fix exists to remove.
      if (h.sell_eligible == null) return false;
      const expect = filters.sell_eligible === "true";
      if (h.sell_eligible !== expect) return false;
    }
    return true;
  });

  // sort
  const { sorted: sortedRows, sortKey, asc, handleSort } = useSortableTable(filtered, "ticker");
  const sortBy = (key: HoldingsSortKey) => handleSort(key);

  const totals = useMemo(
    () =>
      sortedRows.reduce(
        (acc, h) => {
          // Rows with no known gain -- no positive cost, a guessed cost or an
          // implausible booked cost (#7220/#8471/#8472) -- stay out of both
          // the gain and the cost behind the total gain % so they can't skew
          // it. Their cost still counts toward the total cost.
          const gainCounted = h.gain !== null;
          return {
            cost: acc.cost + (h.cost ?? 0),
            market: acc.market + (h.market ?? 0),
            gain: acc.gain + (gainCounted ? h.gain ?? 0 : 0),
            gainCost: acc.gainCost + (gainCounted ? h.cost ?? 0 : 0),
            weight: acc.weight + (h.weight_pct ?? 0),
          };
        },
        { cost: 0, market: 0, gain: 0, gainCost: 0, weight: 0 },
      ),
    [sortedRows],
  );
  const totalGainPct = totals.gainCost
    ? (totals.gain / totals.gainCost) * 100
    : null;
  // Cash rows carry no total return (undefined); a null on any position means
  // its income or gains are unknown, so the total is withheld (#9038).
  const totalReturn = useMemo(() => {
    const positions = sortedRows.filter((h) => h.total_return_gbp !== undefined);
    if (!positions.length || positions.some((h) => h.total_return_gbp == null)) return null;
    return positions.reduce((sum, h) => sum + (h.total_return_gbp ?? 0), 0);
  }, [sortedRows]);

  // Same rule for income: an unknown position withholds the total (#10395).
  const totalIncome = useMemo(() => {
    const positions = sortedRows.filter((h) => h.income_gbp !== undefined);
    if (!positions.length || positions.some((h) => h.income_gbp == null)) return null;
    return positions.reduce((sum, h) => sum + (h.income_gbp ?? 0), 0);
  }, [sortedRows]);

  const categoryLookup = useMemo(
    () => buildCategoryLookup(categoryDefinitions),
    [categoryDefinitions],
  );
  const hasCategories = categoryLookup.categories.size > 0;

  // Category mode requires categoryDefinitions; fall back to 'group' when the
  // caller requests 'category' without providing definitions (matching
  // InstrumentTable's useInstrumentTableState behaviour).
  const effectiveGroupingMode: GroupingMode =
    groupingMode === "category" && !hasCategories ? "group" : groupingMode;

  const groups = useMemo(() => {
    const groupingRows = sortedRows.map((row, index) => ({
      ...row,
      __holdingsIndex: index,
      cost: row.cost,
      market_value_gbp: row.market,
      // A null gain only arises when cost <= 0 (adds nothing to cost totals)
      // or the cost basis is already unreliable (excluded by
      // calculateGroupTotals), so it contributes no gain either (#8471).
      // Group totals that are null (#8531) come from calculateGroupTotals,
      // not from this per-row fallback.
      gain_gbp: row.gain ?? 0,
      change_7d_pct: row.change_7d_pct ?? row.forward_7d_change_pct ?? null,
      change_30d_pct: row.change_30d_pct ?? row.forward_30d_change_pct ?? null,
    })) as RowWithCost[];

    return createGroups(
      groupingRows,
      GROUP_SORT_KEYS[sortKey as HoldingsSortKey],
      asc,
      effectiveGroupingMode,
      {
        ungroupedLabel: t("instrumentTable.ungrouped", { defaultValue: "Ungrouped" }),
        uncategorisedLabel: t("instrumentTable.uncategorised", {
          defaultValue: "Uncategorised",
        }),
        unknownSectorLabel: t("instrumentTable.unknownSector", {
          defaultValue: "Unknown sector",
        }),
      },
      categoryLookup,
    );
  }, [asc, categoryLookup, effectiveGroupingMode, sortKey, sortedRows, t]);
  const overallGroupTotals = useMemo(
    () =>
      calculateGroupTotals(
        groups.flatMap((group) => group.rows),
        t("holdingsTable.totalRowLabel"),
      ),
    [groups, t],
  );
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set());
  const showGroupHeaders = effectiveGroupingMode !== "flat";
  // Rollup rows have no days held. In grouped mode there is no days-held group
  // total (GROUP_SORT_KEYS.days_held is null), but sorting still orders rows
  // within each group, and groups follow their first row in that order.
  const daysHeldSortable = !rollupMode;

  const columnLabels: [ColumnKey, string][] = [
    ["sector", t("holdingsTable.columns.sector")],
    ["units", t("holdingsTable.columns.units")],
    ["market", t("holdingsTable.columns.market", { symbol: reporting.symbol })],
    ["gain", t("holdingsTable.columns.gain", { symbol: reporting.symbol })],
    ["gain_pct", t("holdingsTable.columns.gainPct")],
    ["total_return", t("holdingsTable.columns.totalReturn", { symbol: reporting.symbol })],
    ["income", t("holdingsTable.columns.income", { symbol: reporting.symbol })],
    ["price", t("holdingsTable.columns.price", { symbol: reporting.symbol })],
    ["cost", t("holdingsTable.columns.cost", { symbol: reporting.symbol })],
    ["weight_pct", t("holdingsTable.columns.weightPct")],
    ["trend", t("holdingsTable.columns.trend")],
    ["ccy", t("holdingsTable.columns.ccy")],
    ["type", t("holdingsTable.columns.type")],
    ["acquired", t("holdingsTable.columns.acquired")],
    ["days_held", t("holdingsTable.columns.daysHeld")],
    ["stage", t("holdingsTable.columns.stage")],
    ["eligible", t("holdingsTable.columns.eligible")],
  ];

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const topScrollbarRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const tableHeaderRef = useRef<HTMLTableSectionElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [hasMoreColumns, setHasMoreColumns] = useState(false);
  const [hasHorizontalOverflow, setHasHorizontalOverflow] = useState(false);
  const [tableWidth, setTableWidth] = useState(0);

  // The header row's height changes when columns are toggled or the viewport
  // narrows and titles wrap. It feeds the virtualizer's scrollMargin, so it has
  // to be re-measured on resize rather than once on mount.
  useLayoutEffect(() => {
    const header = tableHeaderRef.current;
    if (!header) return;

    const measure = () =>
      setHeaderHeight((previous) => {
        const next = header.getBoundingClientRect().height;
        return Math.abs(next - previous) < 0.5 ? previous : next;
      });

    measure();

    if (typeof ResizeObserver === "undefined") return;
    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(header);
    return () => resizeObserver.disconnect();
  }, [sortedRows.length]);

  useLayoutEffect(() => {
    const container = tableContainerRef.current;
    const topScrollbar = topScrollbarRef.current;
    const table = tableRef.current;
    if (!container || !topScrollbar || !table) return;

    const updateOverflowCue = () => {
      const remainingScroll =
        container.scrollWidth - container.clientWidth - container.scrollLeft;
      setHasMoreColumns(remainingScroll > 1);
      setHasHorizontalOverflow(container.scrollWidth - container.clientWidth > 1);
      setTableWidth(table.scrollWidth);
    };

    const syncFromTable = () => {
      topScrollbar.scrollLeft = container.scrollLeft;
      updateOverflowCue();
    };
    const syncFromTopScrollbar = () => {
      container.scrollLeft = topScrollbar.scrollLeft;
      updateOverflowCue();
    };

    updateOverflowCue();
    container.addEventListener("scroll", syncFromTable, { passive: true });
    topScrollbar.addEventListener("scroll", syncFromTopScrollbar, { passive: true });
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(updateOverflowCue);
    resizeObserver?.observe(container);
    resizeObserver?.observe(table);

    return () => {
      container.removeEventListener("scroll", syncFromTable);
      topScrollbar.removeEventListener("scroll", syncFromTopScrollbar);
      resizeObserver?.disconnect();
    };
  }, [sortedRows.length, relativeViewEnabled, visibleColumns, showForward7d, showForward30d]);

  // Grouped mode disables the virtualizer (count=0) so that all group headers
  // and their rows remain addressable in the DOM regardless of expand/collapse
  // state. This renders every row at once — acceptable for the typical grouped
  // view size (tens of groups) but should be revisited before wiring this mode
  // to pages that display hundreds of holdings.
  const rowVirtualizer = useVirtualizer({
    count: showGroupHeaders ? 0 : sortedRows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5,
    scrollMargin: headerHeight,
  });
  const virtualRows = showGroupHeaders ? [] : rowVirtualizer.getVirtualItems();
  const { paddingTop, paddingBottom } = getVirtualSpacerHeights(
    virtualRows,
    rowVirtualizer.getTotalSize(),
    rowVirtualizer.options.scrollMargin,
  );
  const spacerColSpan =
    ALWAYS_VISIBLE_COLUMN_COUNT +
    (showAccount ? 1 : 0) +
    (showForward7d ? 1 : 0) +
    (showForward30d ? 1 : 0) +
    (Object.keys(visibleColumns) as ColumnKey[]).filter(show).length;
  // Ticker + name (+ sector) share the label cell in group and total rows.
  const labelColSpan = ALWAYS_VISIBLE_COLUMN_COUNT + (show("sector") ? 1 : 0);
  // Grouped mode walks the groups in their own (totals-sorted) order so each
  // group's rows stay contiguous under its header (#8529). Every grouped row
  // comes from groupingRows above, which always stamps __holdingsIndex.
  const groupByIndex = useMemo(() => {
    const lookup = new Map<number, GroupedRows>();
    for (const group of groups) {
      for (const row of group.rows) {
        lookup.set((row as IndexedGroupRow).__holdingsIndex, group);
      }
    }
    return lookup;
  }, [groups]);
  const items: { index: number }[] = showGroupHeaders
    ? groups.flatMap((group) =>
        group.rows.map((row) => ({ index: (row as IndexedGroupRow).__holdingsIndex })),
      )
    : virtualRows.length
      ? virtualRows
      : sortedRows.map((_, index) => ({ index }));

  const renderGroupHeader = (group: GroupedRows, expanded: boolean) => {
    const groupDomId = `holdings-group-${sanitizeGroupKey(group.key)}`;
    const groupWeight = overallGroupTotals.marketValue
      ? (group.totals.marketValue / overallGroupTotals.marketValue) * 100
      : 0;

    return (
      <tr key={`group-${group.key}`} className={tableStyles.groupRow}>
        {showAccount && <td className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>}
        <th
          scope="row"
          className={`${tableStyles.cell} ${tableStyles.groupCell}`}
          colSpan={labelColSpan}
        >
          <button
            type="button"
            className={tableStyles.groupToggle}
            onClick={() =>
              setExpandedGroups((previous) => {
                const next = new Set(previous);
                if (next.has(group.key)) next.delete(group.key);
                else next.add(group.key);
                return next;
              })
            }
            aria-expanded={expanded}
            aria-controls={groupDomId}
            aria-label={t("instrumentTable.groupToggle", {
              group: group.label,
              defaultValue: `Toggle ${group.label}`,
            })}
          >
            <span aria-hidden="true" className={tableStyles.groupToggleIcon}>
              {expanded ? "−" : "+"}
            </span>
            <span>{group.label}</span>
            <span className={tableStyles.groupCount}>({group.rows.length})</span>
          </button>
        </th>
        {show("units") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {/* Units summed across different instruments mean nothing (#8531). */}
            {group.totals.instrumentCount > 1
              ? "—"
              : new Intl.NumberFormat(i18n.language).format(group.totals.units)}
          </td>
        )}
        {show("market") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {reporting.format(group.totals.marketValue)}
          </td>
        )}
        {show("gain") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {group.totals.gain === null ? (
              <span
                className={tableStyles.notApplicable}
                title={t("holdingsTable.gainNotAvailable")}
              >
                {t("holdingsTable.notApplicable")}
              </span>
            ) : (
              reporting.format(group.totals.gain)
            )}
          </td>
        )}
        {show("gain_pct") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {percent(group.totals.gainPct, 1)}
          </td>
        )}
        {show("total_return") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>—</td>
        )}
        {show("income") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>—</td>
        )}
        {show("price") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>—</td>
        )}
        {show("cost") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {group.totals.cost === null ? (
              <span
                className={tableStyles.notApplicable}
                title={t("holdingsTable.gainNotAvailable")}
              >
                {t("holdingsTable.notApplicable")}
              </span>
            ) : (
              reporting.format(group.totals.cost)
            )}
          </td>
        )}
        {showForward7d && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {percent(group.totals.change7dPct, 1)}
          </td>
        )}
        {showForward30d && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {percent(group.totals.change30dPct, 1)}
          </td>
        )}
        {show("weight_pct") && (
          <td className={`${tableStyles.cell} ${tableStyles.groupCell} ${tableStyles.right}`}>
            {percent(groupWeight, 1)}
          </td>
        )}
        {Array.from({ length: trailingColumnCount }, (_, index) => (
          <td key={index} className={`${tableStyles.cell} ${tableStyles.groupCell}`}>—</td>
        ))}
      </tr>
    );
  };

  return (
    <>
      {missingHistoryTickers.length > 0 && (
        <p role="status" className="mb-2 text-sm text-warning">
          {t("holdingsTable.noPriceHistoryNotice", {
            count: missingHistoryTickers.length,
          })}
        </p>
      )}
      {/* FilterBar and all advanced controls are hidden in Family MVP mode */}
      {!familyMvpEnabled && (
        <>
          <FilterBar state={filters} dispatch={dispatchFilters} />
          <HoldingsFilterControls
            sparkRange={sparkRange}
            onSparkRangeChange={setSparkRange}
            viewPresets={viewPresets}
            viewPreset={viewPreset}
            onViewPresetChange={setViewPreset}
            minimumGain={filters.gain_pct}
            onMinimumGainChange={(value) => handleFilterChange("gain_pct", value)}
            onSellEligible={
              rollupMode
                ? undefined
                : () => handleFilterChange("sell_eligible", "true")
            }
          />
          {/* Presets set the per-column checkboxes below rather than replacing them (#7832). */}
          <div
            role="group"
            aria-label={t("holdingsTable.columnPresets.label")}
            className="mb-1 flex flex-wrap items-center gap-1"
          >
            {t("holdingsTable.columnPresets.label")}
            {(Object.keys(COLUMN_PRESETS) as ColumnPreset[]).map((preset) => (
              <button
                key={preset}
                type="button"
                aria-pressed={activeColumnPreset === preset}
                onClick={() => setVisibleColumns({ ...COLUMN_PRESETS[preset] })}
                className={`ml-1 ${activeColumnPreset === preset ? "font-bold" : ""} focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500`}
              >
                {t(`holdingsTable.columnPresets.${preset}`)}
              </button>
            ))}
          </div>
          <div
            role="group"
            aria-label={t("holdingsTable.columnsLabel")}
            className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1"
          >
            {t("holdingsTable.columnsLabel")}
            {columnLabels.map(([key, label]) => (
              <label key={key} className="ml-1">
                <input
                  type="checkbox"
                  checked={visibleColumns[key]}
                  onChange={() => toggleColumn(key)}
                />
                {label}
              </label>
            ))}
          </div>
        </>
      )}
      {/* Per-column filters live above the table rather than in a second
          <thead> row: that row rendered as a blank band with placeholder text
          floating over the real headers (#7814). Rendering them outside the
          table also keeps them reachable when a filter matches nothing. */}
      {holdings.length > 0 && (
        <div
          role="group"
          aria-label={t("holdingsTable.filtersLabel")}
          className="mb-2 flex flex-wrap items-center gap-2"
        >
          <input
            className="w-28"
            placeholder={t("holdingsTable.filters.ticker")}
            aria-label={t("holdingsTable.filterBy", { field: t("holdingsTable.filters.ticker") })}
            value={filters.ticker}
            onChange={(e) => handleFilterChange("ticker", e.target.value)}
          />
          <input
            className="w-36"
            placeholder={t("holdingsTable.filters.name")}
            aria-label={t("holdingsTable.filterBy", { field: t("holdingsTable.filters.name") })}
            value={filters.name}
            onChange={(e) => handleFilterChange("name", e.target.value)}
          />
          {show("units") && (
            <input
              className="w-24"
              placeholder={t("holdingsTable.filters.units")}
              aria-label={t("holdingsTable.filterBy", { field: t("holdingsTable.filters.units") })}
              value={filters.units}
              onChange={(e) => handleFilterChange("units", e.target.value)}
            />
          )}
          {show("gain_pct") && (
            <input
              className="w-24"
              placeholder={t("holdingsTable.filters.gainPct")}
              aria-label={t("holdingsTable.filterBy", { field: t("holdingsTable.filters.gainPct") })}
              value={filters.gain_pct}
              onChange={(e) => handleFilterChange("gain_pct", e.target.value)}
            />
          )}
          {show("type") && (
            <input
              className="w-28"
              placeholder={t("holdingsTable.filters.type")}
              aria-label={t("holdingsTable.filterBy", { field: t("holdingsTable.filters.type") })}
              value={filters.instrument_type}
              onChange={(e) => handleFilterChange("instrument_type", e.target.value)}
            />
          )}
          {show("eligible") && !rollupMode && (
            <select
              aria-label={t("holdingsTable.filters.sellEligible")}
              value={filters.sell_eligible}
              onChange={(e) => handleFilterChange("sell_eligible", e.target.value)}
            >
              <option value="">{t("holdingsTable.filters.all")}</option>
              <option value="true">{t("holdingsTable.filters.yes")}</option>
              <option value="false">{t("holdingsTable.filters.no")}</option>
            </select>
          )}
        </div>
      )}
      {sortedRows.length ? (
        <>
          {hasMoreColumns && (
            <p className={tableStyles.moreColumnsHint} aria-hidden="true">
              {t("holdingsTable.moreColumnsHint")}
            </p>
          )}
          <div
            ref={topScrollbarRef}
            className={`${tableStyles.topScrollbar} ${hasHorizontalOverflow ? "" : tableStyles.topScrollbarHidden}`}
            role="region"
            aria-label={t("holdingsTable.horizontalScroll")}
            aria-hidden={!hasHorizontalOverflow}
            tabIndex={hasHorizontalOverflow ? 0 : -1}
          >
            <div className={tableStyles.topScrollbarContent} style={{ width: tableWidth }} />
          </div>
          <div
            ref={tableContainerRef}
            className={`${tableStyles.scrollContainer} ${hasMoreColumns ? tableStyles.hasMoreColumns : ""}`}
          >
            <table ref={tableRef} className={`${tableStyles.table} mb-4 w-full`}>
        <thead ref={tableHeaderRef}>
          <tr>
            {showAccount && (
              <th className={tableStyles.cell}>{t("holdingsTable.columns.account")}</th>
            )}
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => sortBy("ticker")}
              aria-label={t("holdingsTable.columns.ticker")}
            >
              {t("holdingsTable.columns.ticker")}{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.clickable}`} onClick={() => sortBy("name")}>
              {t("holdingsTable.columns.name")}{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            {show("sector") && (
              <th className={`${tableStyles.cell} ${tableStyles.clickable}`} onClick={() => sortBy("sector")}>
                {t("holdingsTable.columns.sector")}{sortKey === "sector" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("units") && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.units")}</th>
            )}
            {show("market") && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.market", { symbol: reporting.symbol })}</th>
            )}
            {show("gain") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("gain")}
              >
                {t("holdingsTable.columns.gain", { symbol: reporting.symbol })}{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("gain_pct") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("gain_pct")}
              >
                {t("holdingsTable.columns.gainPct")}{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("total_return") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                title={t("holdingsTable.totalReturnHeaderTitle")}
                onClick={() => sortBy("total_return_gbp")}
              >
                {t("holdingsTable.columns.totalReturn", { symbol: reporting.symbol })}{sortKey === "total_return_gbp" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("income") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                title={t("holdingsTable.incomeHeaderTitle")}
                onClick={() => sortBy("income_gbp")}
              >
                {t("holdingsTable.columns.income", { symbol: reporting.symbol })}{sortKey === "income_gbp" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("price") && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.price", { symbol: reporting.symbol })}</th>
            )}
            {show("cost") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("cost")}
              >
                {t("holdingsTable.columns.cost", { symbol: reporting.symbol })}{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {showForward7d && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("forward_7d_change_pct")}
              >
                {t("holdingsTable.columns.forward7d")}
                {sortKey === "forward_7d_change_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {showForward30d && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("forward_30d_change_pct")}
              >
                {t("holdingsTable.columns.forward30d")}
                {sortKey === "forward_30d_change_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("weight_pct") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => sortBy("weight_pct")}
              >
                {t("holdingsTable.columns.weightPct")}{sortKey === "weight_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("trend") && (
              <th className={`${tableStyles.cell} ${tableStyles.trend}`}>
                {t("holdingsTable.trendHeader", { range: sparkRange })}
              </th>
            )}
            {show("ccy") && (
              <th className={tableStyles.cell}>{t("instrumentTable.columns.ccy")}</th>
            )}
            {show("type") && (
              <th className={tableStyles.cell}>{t("instrumentTable.columns.type")}</th>
            )}
            {show("acquired") && (
              <th className={tableStyles.cell}>{t("holdingsTable.columns.acquired")}</th>
            )}
            {show("days_held") && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right}${daysHeldSortable ? ` ${tableStyles.clickable}` : ""}`}
                onClick={daysHeldSortable ? () => sortBy("days_held") : undefined}
              >
                {t("holdingsTable.columns.daysHeld")}
                {daysHeldSortable && sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {show("stage") && (
              <th className={`${tableStyles.cell} ${tableStyles.center}`}>{t("holdingsTable.columns.stage")}</th>
            )}
            {show("eligible") && (
              <th className={`${tableStyles.cell} ${tableStyles.center}`}>{t("holdingsTable.columns.eligible")}</th>
            )}
          </tr>
        </thead>

        <tbody>
          {paddingTop > 0 && (
            <tr style={{ height: paddingTop }}>
              <td colSpan={spacerColSpan} className="p-0 border-0" />
            </tr>
          )}
          {items.map((virtualRow) => {
            const h = sortedRows[virtualRow.index];
            const group = showGroupHeaders ? groupByIndex.get(virtualRow.index) : undefined;
            const isFirstGroupRow =
              (group?.rows[0] as IndexedGroupRow | undefined)?.__holdingsIndex ===
              virtualRow.index;
            const expanded = group ? expandedGroups.has(group.key) : true;
            if (group && !expanded && !isFirstGroupRow) return null;
            const isSelected = h.ticker === selectedTicker;
            const handleSelect = () => {
              onSelectInstrument?.(h.ticker, h.name ?? h.ticker, h.instrument_type);
            };
            const tooltip = instrumentTooltip(t, h.ticker, h.name, h.instrument_type);
            const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              event.stopPropagation();
              handleSelect();
            };
            const holdingRow = (
              <tr
                ref={rowVirtualizer.measureElement}
                data-index={virtualRow.index}
                id={group && isFirstGroupRow ? `holdings-group-${sanitizeGroupKey(group.key)}` : undefined}
                key={h.row_key ?? h.ticker + h.acquired_date}
                onClick={onSelectInstrument ? handleSelect : undefined}
                aria-selected={isSelected || undefined}
                className={[
                  onSelectInstrument ? tableStyles.clickable : undefined,
                  isSelected ? tableStyles.selected : undefined,
                ]
                  .filter(Boolean)
                  .join(" ") || undefined}
              >
                {showAccount && (
                  <td className={tableStyles.cell}>{h.source_account}</td>
                )}
                <td className={tableStyles.cell}>
                  <button
                    type="button"
                    onClick={handleClick}
                    title={tooltip}
                    className="link-button focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
                  >
                    {h.ticker}
                  </button>
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.name}`} title={tooltip}>{h.name}</td>
                {show("sector") && (
                  <td className={tableStyles.cell}>{h.sector || "—"}</td>
                )}
                {show("units") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {new Intl.NumberFormat(i18n.language).format(h.units ?? 0)}
                  </td>
                )}
                {show("market") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {reporting.format(h.market, h.market_value_currency)}
                  </td>
                )}
                {show("gain") && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${h.gain === null ? "" : getPerformanceClass(h.gain)}`}
                  >
                    {h.gain === null ? (
                      <span
                        className={tableStyles.notApplicable}
                        title={gainWithheldTitle(h.cost_basis_source)}
                      >
                        {t("holdingsTable.notApplicable")}
                      </span>
                    ) : (
                      reporting.format(h.gain, h.gain_currency)
                    )}
                  </td>
                )}
                {show("gain_pct") && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${h.gain_pct === null ? "" : getPerformanceClass(h.gain_pct)}`}
                  >
                    {h.gain_pct === null ? (
                      <span
                        className={tableStyles.notApplicable}
                        title={gainWithheldTitle(h.cost_basis_source)}
                      >
                        {t("holdingsTable.notApplicable")}
                      </span>
                    ) : (
                      percent(h.gain_pct, 1)
                    )}
                  </td>
                )}
                {show("total_return") && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${h.total_return_gbp == null ? "" : getPerformanceClass(h.total_return_gbp)}`}
                    title={totalReturnTitle(h)}
                  >
                    {h.total_return_gbp === undefined ? (
                      "—"
                    ) : h.total_return_gbp === null ? (
                      <span className={tableStyles.notApplicable}>{t("holdingsTable.notApplicable")}</span>
                    ) : (
                      h.total_return_pct == null
                        ? reporting.format(h.total_return_gbp)
                        : `${reporting.format(h.total_return_gbp)} (${percent(h.total_return_pct, 1)})`
                    )}
                  </td>
                )}
                {show("income") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`} title={incomeTitle(h)}>
                    {h.income_gbp === undefined ? (
                      "—"
                    ) : h.income_gbp === null ? (
                      <span className={tableStyles.notApplicable}>{t("holdingsTable.notApplicable")}</span>
                    ) : (
                      `${h.income_estimated ? "≈" : ""}${reporting.format(h.income_gbp)}`
                    )}
                  </td>
                )}
                {show("price") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    <span className={h.is_stale ? "text-gray" : undefined}>
                      {reporting.format(h.current_price_gbp, h.current_price_currency)}
                    </span>
                    {h.is_stale && (
                      <span
                        className="ml-1 text-warning"
                        title={h.last_price_time ?? undefined}
                      >
                        *
                      </span>
                    )}
                    {isFxRateFlagged(h.fx_rate_source) && (
                      // Approximate or absent FX rate (#9664, #9730).
                      <span
                        className="ml-1 text-warning"
                        title={fxRateTitle(h.fx_rate_source)}
                        aria-label={fxRateTitle(h.fx_rate_source)}
                      >
                        {h.fx_rate_source === FX_RATE_SOURCE_MISSING ? "FX" : "≈"}
                      </span>
                    )}
                    {h.last_price_date && (
                      <span
                        className={tableStyles.badge}
                        title={h.last_price_date}
                      >
                        {formatDateISO(new Date(h.last_price_date))}
                      </span>
                    )}
                  </td>
                )}
                {show("cost") && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right}`}
                    title={
                      h.cost_basis_source === "unknown"
                        ? t("holdingsTable.costBasisUnknown")
                        : h.cost_basis_source === COST_BASIS_BOOK_SUSPECT
                          ? t("holdingsTable.bookCostSuspect")
                          : (h.cost_basis_gbp ?? 0) > 0
                          ? t("holdingsTable.actualPurchaseCost")
                          : t("holdingsTable.inferredCost")
                    }
                  >
                    {reporting.format(
                      h.cost,
                      h.cost_basis_currency || h.effective_cost_basis_currency,
                    )}
                  </td>
                )}
                {showForward7d && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${getPerformanceClass(h.forward_7d_change_pct)}`}
                  >
                    {percent(h.forward_7d_change_pct ?? null, 1)}
                  </td>
                )}
                {showForward30d && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${getPerformanceClass(h.forward_30d_change_pct)}`}
                  >
                    {percent(h.forward_30d_change_pct ?? null, 1)}
                  </td>
                )}
                {show("weight_pct") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {percent(h.weight_pct ?? 0, 1)}
                  </td>
                )}
                {show("trend") && (
                  <td className={`${tableStyles.cell} ${tableStyles.trend}`}>
                    <Sparkline
                      ticker={h.ticker}
                      days={sparkRange}
                      width={80}
                      ariaLabel={t("holdingsTable.sparklineAria", { ticker: h.ticker })}
                    />
                  </td>
                )}
                {show("ccy") && (
                  <td className={tableStyles.cell}>
                    {isSupportedFx(h.currency) ? (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectInstrument?.(`${h.currency!}GBP.FX`, h.currency!);
                        }}
                        className="link-button"
                      >
                        {h.currency}
                      </button>
                    ) : (
                      h.currency ?? "—"
                    )}
                  </td>
                )}
                {show("type") && (
                  <td className={tableStyles.cell}>
                    {translateInstrumentType(t, h.instrument_type)}
                  </td>
                )}
                {show("acquired") && (
                  <td className={tableStyles.cell}>
                    {h.acquired_date && !isNaN(Date.parse(h.acquired_date))
                      ? formatDateISO(new Date(h.acquired_date))
                      : (
                          <span
                            className={tableStyles.notApplicable}
                            title={t("holdingsTable.acquiredNotAvailable")}
                          >
                            {t("holdingsTable.notApplicable")}
                          </span>
                        )}
                  </td>
                )}
                {show("days_held") && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {h.days_held ?? (
                      <span
                        className={tableStyles.notApplicable}
                        title={t("holdingsTable.daysHeldNotAvailable")}
                      >
                        {t("holdingsTable.notApplicable")}
                      </span>
                    )}
                  </td>
                )}
                {show("stage") && (
                  <td className={`${tableStyles.cell} ${tableStyles.center}`}>
                    {h.days_held != null
                      ? (() => {
                          const stage = getGrowthStage({ daysHeld: h.days_held });
                          return <span title={stage.message}>{stage.icon}</span>;
                        })()
                      : (
                          <span
                            className={tableStyles.notApplicable}
                            title={t("holdingsTable.stageNotAvailable")}
                          >
                            {t("holdingsTable.notApplicable")}
                          </span>
                        )}
                  </td>
                )}
                {show("eligible") && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.center} ${
                      h.sell_eligible == null
                        ? ""
                        : h.sell_eligible
                          ? "text-positive"
                          : "text-warning"
                    }`}
                    title={
                      h.next_eligible_sell_date
                        ? formatDateISO(new Date(h.next_eligible_sell_date))
                        : h.sell_eligible == null
                          ? t("holdingsTable.eligibleNotAvailable")
                          : undefined
                    }
                  >
                    {h.sell_eligible == null ||
                    (!h.sell_eligible &&
                      h.days_until_eligible == null &&
                      !h.next_eligible_sell_date) ? (
                      // An unknown hold period yields no verdict (#7196).
                      <span className={tableStyles.notApplicable}>
                        {t("holdingsTable.notApplicable")}
                      </span>
                    ) : h.sell_eligible ? (
                      `✓ ${t("holdingsTable.eligible")}`
                    ) : h.days_until_eligible ? (
                      `✗ ${t("holdingsTable.eligibleInDays", { count: h.days_until_eligible })}`
                    ) : (
                      // Hold period elapsed (a known eligible date with no
                      // countdown left -- null since #7242, 0 in older
                      // payloads) but still not eligible: the sale needs
                      // approval. Say so instead of a cryptic "✗ 0" (#7196).
                      `✗ ${t("holdingsTable.eligibleNeedsApproval")}`
                    )}
                  </td>
                )}
              </tr>
            );
            if (!group) return holdingRow;
            return (
              <Fragment key={`section-${group.key}-${h.row_key ?? virtualRow.index}`}>
                {isFirstGroupRow && renderGroupHeader(group, expanded)}
                {expanded && holdingRow}
              </Fragment>
            );
          })}
          {paddingBottom > 0 && (
            <tr style={{ height: paddingBottom }}>
              <td colSpan={spacerColSpan} className="p-0 border-0" />
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <td
              className={`${tableStyles.cell} font-semibold`}
              colSpan={labelColSpan + (showAccount ? 1 : 0)}
            >
              {t("holdingsTable.totalRowLabel")}
            </td>
            {show("units") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {show("market") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {reporting.format(totals.market)}
              </td>
            )}
            {show("gain") && (
              <td
                className={`${tableStyles.cell} ${tableStyles.right} font-semibold ${getPerformanceClass(totals.gain)}`}
              >
                {reporting.format(totals.gain)}
              </td>
            )}
            {show("gain_pct") && (
              <td
                className={`${tableStyles.cell} ${tableStyles.right} font-semibold ${getPerformanceClass(totalGainPct)}`}
              >
                {percent(totalGainPct, 1)}
              </td>
            )}
            {show("total_return") && (
              <td
                className={`${tableStyles.cell} ${tableStyles.right} font-semibold ${totalReturn === null ? "" : getPerformanceClass(totalReturn)}`}
              >
                {totalReturn === null ? "—" : reporting.format(totalReturn)}
              </td>
            )}
            {show("income") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {totalIncome === null ? "—" : reporting.format(totalIncome)}
              </td>
            )}
            {show("price") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {show("cost") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {reporting.format(totals.cost)}
              </td>
            )}
            {showForward7d && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {showForward30d && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {show("weight_pct") && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {percent(totals.weight, 1)}
              </td>
            )}
            {Array.from({ length: trailingColumnCount }, (_, index) => (
              <td key={index} className={tableStyles.cell}></td>
            ))}
          </tr>
        </tfoot>
            </table>
          </div>
        </>
      ) : (
        <EmptyState
          message={t("holdingsTable.noHoldings")}
          actions={[
            ...(onAddPosition && holdings.length === 0
              ? [{ label: t("addPosition.emptyAccountCta"), onClick: onAddPosition }]
              : []),
            { label: t("holdingsTable.clearFilters"), onClick: clearFilters },
            { label: t("holdingsTable.openScreener"), onClick: () => navigate("/screener") },
          ]}
        />
      )}
    </>
  );
}
