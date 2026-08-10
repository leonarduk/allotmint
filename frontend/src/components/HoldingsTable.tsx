import { useState, useEffect, useRef, useMemo, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Holding } from "../types";
import { money, percent } from "../lib/money";
import { translateInstrumentType } from "../lib/instrumentType";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";
import { useConfig } from "../ConfigContext";
import { isSupportedFx } from "../lib/fx";
import { formatDateISO } from "../lib/date";
import { RelativeViewToggle } from "./RelativeViewToggle";
import FilterBar, { useFilterReducer, type FilterState } from "./FilterBar";
import EmptyState from "./EmptyState";
import { useNavigate } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import Sparkline from "./Sparkline";
import { getGrowthStage } from "../utils/growthStage";
import { preloadInstrumentHistory } from "../hooks/useInstrumentHistory";

const VIEW_PRESET_STORAGE_KEY = "holdingsTableViewPreset";

type HoldingsTableRow = Holding & {
  source_account?: string;
  row_key?: string;
};

type Props = {
  holdings: HoldingsTableRow[];
  showAccount?: boolean;
  onSelectInstrument?: (ticker: string, name: string) => void;
  showForward7d?: boolean;
  showForward30d?: boolean;
  onAddPosition?: () => void;
};


export function HoldingsTable({
  holdings,
  showAccount = false,
  onSelectInstrument,
  showForward7d = false,
  showForward30d = false,
  onAddPosition,
}: Props) {
  const { t } = useTranslation();
  const { relativeViewEnabled, baseCurrency, familyMvpEnabled } = useConfig();
  let navigate: (path: string) => void = () => {};
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    navigate = useNavigate();
  } catch {
    // Intentional: component may be rendered outside a Router in tests/storybook.
    // useNavigate() is only used for the EmptyState screener shortcut.
  }

  const viewPresets = useMemo(
    () => [
      { label: t("holdingsTable.viewPresets.all"), value: "" },
      { label: t("instrumentType.etf"), value: "ETF" },
      { label: t("instrumentType.equity"), value: "Equity" },
      { label: t("instrumentType.bond"), value: "Bond" },
    ],
    [t],
  );

  const [filters, dispatchFilters] = useFilterReducer();

  const [viewPreset, setViewPreset] = useState(() =>
    typeof window === "undefined"
      ? ""
      : localStorage.getItem(VIEW_PRESET_STORAGE_KEY) || ""
  );

  const [visibleColumns, setVisibleColumns] = useState({
    units: true,
    cost: true,
    market: true,
    gain: true,
    gain_pct: true,
  });

  const [sparkRange, setSparkRange] = useState<7 | 30 | 180>(30);

  useEffect(() => {
    const tickers = Array.from(new Set(holdings.map((h) => h.ticker)));
    if (tickers.length) {
      preloadInstrumentHistory(tickers, sparkRange).catch(() => {});
    }
  }, [holdings, sparkRange]);

  const toggleColumn = (key: keyof typeof visibleColumns) => {
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


  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(VIEW_PRESET_STORAGE_KEY, viewPreset);
    }
    dispatchFilters({ type: "set", key: "instrument_type", value: viewPreset });
    // dispatchFilters is stable (useReducer dispatch), including it satisfies exhaustive-deps without risk
  }, [viewPreset, dispatchFilters]);

  // derive cost/market/gain/gain_pct
  const computed = holdings.map((h) => {
    const cost =
      (h.cost_basis_gbp ?? 0) > 0
        ? h.cost_basis_gbp ?? 0
        : h.effective_cost_basis_gbp ?? 0;

    const market = h.market_value_gbp ?? 0;
    const gain =
      h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
        ? h.gain_gbp
        : market - cost;

    const gain_pct =
      h.gain_pct !== undefined && h.gain_pct !== null
        ? h.gain_pct
        : cost
          ? (gain / cost) * 100
          : 0;

    return { ...h, cost, market, gain, gain_pct };
  });

  const totalMarket = computed.reduce((sum, h) => sum + (h.market ?? 0), 0);
  const rows = computed.map((h) => ({
    ...h,
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
      if (!Number.isNaN(minGain) && (h.gain_pct ?? 0) < minGain) return false;
    }
    if (filters.sell_eligible) {
      const expect = filters.sell_eligible === "true";
      if (!!h.sell_eligible !== expect) return false;
    }
    return true;
  });

  // sort
  const { sorted: sortedRows, sortKey, asc, handleSort } = useSortableTable(filtered, "ticker");

  const totals = useMemo(
    () =>
      sortedRows.reduce(
        (acc, h) => ({
          cost: acc.cost + (h.cost ?? 0),
          market: acc.market + (h.market ?? 0),
          gain: acc.gain + (h.gain ?? 0),
          weight: acc.weight + (h.weight_pct ?? 0),
        }),
        { cost: 0, market: 0, gain: 0, weight: 0 },
      ),
    [sortedRows],
  );
  const totalGainPct = totals.cost ? (totals.gain / totals.cost) * 100 : 0;

  const columnLabels: [keyof typeof visibleColumns, string][] = [
    ["units", t("holdingsTable.columns.units")],
    ["cost", t("holdingsTable.columns.cost")],
    ["market", t("holdingsTable.columns.market")],
    ["gain", t("holdingsTable.columns.gain")],
    ["gain_pct", t("holdingsTable.columns.gainPct")],
  ];

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const topScrollbarRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const tableHeaderRef = useRef<HTMLTableSectionElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [hasMoreColumns, setHasMoreColumns] = useState(false);
  const [hasHorizontalOverflow, setHasHorizontalOverflow] = useState(false);
  const [tableWidth, setTableWidth] = useState(0);

  useEffect(() => {
    if (tableHeaderRef.current) {
      setHeaderHeight(tableHeaderRef.current.getBoundingClientRect().height);
    }
  }, []);

  useEffect(() => {
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

  const rowVirtualizer = useVirtualizer({
    count: sortedRows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 40,
    overscan: 5,
    scrollMargin: headerHeight,
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length ? virtualRows[0].start : 0;
  const paddingBottom = virtualRows.length
    ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
    : 0;
  const items = virtualRows.length
    ? virtualRows
    : sortedRows.map((_, index) => ({ index, start: index * 40, end: (index + 1) * 40 }));

  return (
    <>
      {/* FilterBar and all advanced controls are hidden in Family MVP mode */}
      {!familyMvpEnabled && (
        <>
          <FilterBar state={filters} dispatch={dispatchFilters} />
          <div className="mb-2">
            <RelativeViewToggle />
          </div>
          <div className="mb-2">
            {t("holdingsTable.range")}
            {[7, 30, 180].map((d) => (
              <label key={d} className="ml-2">
                <input
                  type="radio"
                  name="sparkRange"
                  checked={sparkRange === d}
                  onChange={() => setSparkRange(d as 7 | 30 | 180)}
                />
                {t("holdingsTable.rangeOption", { count: d })}
              </label>
            ))}
          </div>
          <div className="mb-2">
            {t("holdingsTable.view")}
            {viewPresets.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setViewPreset(p.value)}
                className={`ml-2 ${viewPreset === p.value ? 'font-bold' : ''} focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="mb-2">
            {t("holdingsTable.quickFilters")}
            <button
              type="button"
              className="ml-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
              onClick={() => handleFilterChange("sell_eligible", "true")}
            >
              {t("holdingsTable.quickFiltersSellEligible")}
            </button>
            <input
              type="number"
              placeholder={t("holdingsTable.minimumGainPrompt")}
              value={filters.gain_pct}
              onChange={(e) => handleFilterChange("gain_pct", e.target.value)}
              className="ml-2"
            />
          </div>
          <div className="mb-2">
            {t("holdingsTable.columnsLabel")}
            {columnLabels.map(([key, label]) => (
              <label key={key} className="ml-2">
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
      {sortedRows.length ? (
        <>
          <div
            ref={topScrollbarRef}
            className={`${tableStyles.topScrollbar} ${hasHorizontalOverflow ? "" : tableStyles.topScrollbarHidden}`}
            aria-label={t("holdingsTable.horizontalScroll")}
            tabIndex={0}
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
            {showAccount && <th className={tableStyles.cell}></th>}
            <th className={tableStyles.cell}>
              <input
                placeholder={t("holdingsTable.filters.ticker")}
                value={filters.ticker}
                onChange={(e) => handleFilterChange("ticker", e.target.value)}
              />
            </th>
            <th className={tableStyles.cell}>
              <input
                placeholder={t("holdingsTable.filters.name")}
                value={filters.name}
                onChange={(e) => handleFilterChange("name", e.target.value)}
              />
            </th>
            {!relativeViewEnabled && visibleColumns.units && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                <input
                  placeholder={t("holdingsTable.filters.units")}
                  value={filters.units}
                  onChange={(e) => handleFilterChange("units", e.target.value)}
                />
              </th>
            )}
            {!relativeViewEnabled && visibleColumns.market && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            )}
            {!relativeViewEnabled && visibleColumns.gain && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            )}
            {visibleColumns.gain_pct && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                <input
                  placeholder={t("holdingsTable.filters.gainPct")}
                  value={filters.gain_pct}
                  onChange={(e) => handleFilterChange("gain_pct", e.target.value)}
                />
              </th>
            )}
            <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            {!relativeViewEnabled && visibleColumns.cost && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            )}
            {showForward7d && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            )}
            {showForward30d && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            )}
            <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            <th className={tableStyles.cell}></th>
            <th className={tableStyles.cell}></th>
            <th className={tableStyles.cell}>
              <input
                placeholder={t("holdingsTable.filters.type")}
                value={filters.instrument_type}
                onChange={(e) => handleFilterChange("instrument_type", e.target.value)}
              />
            </th>
            <th className={tableStyles.cell}></th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            <th className={tableStyles.cell}></th>
            <th className={`${tableStyles.cell} ${tableStyles.center}`}>
              <select
                aria-label={t("holdingsTable.filters.sellEligible")}
                value={filters.sell_eligible}
                onChange={(e) => handleFilterChange("sell_eligible", e.target.value)}
              >
                <option value="">{t("holdingsTable.filters.all")}</option>
                <option value="true">{t("holdingsTable.filters.yes")}</option>
                <option value="false">{t("holdingsTable.filters.no")}</option>
              </select>
            </th>
          </tr>
          <tr>
            {showAccount && (
              <th className={tableStyles.cell}>Account</th>
            )}
            <th
              className={`${tableStyles.cell} ${tableStyles.clickable}`}
              onClick={() => handleSort("ticker")}
              aria-label={t("holdingsTable.columns.ticker")}
            >
              {t("holdingsTable.columns.ticker")}{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.clickable}`} onClick={() => handleSort("name")}>
              {t("holdingsTable.columns.name")}{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            {!relativeViewEnabled && visibleColumns.units && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.units")}</th>
            )}
            {!relativeViewEnabled && visibleColumns.market && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.market")}</th>
            )}
            {!relativeViewEnabled && visibleColumns.gain && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("gain")}
              >
                {t("holdingsTable.columns.gain")}{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {visibleColumns.gain_pct && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("gain_pct")}
              >
                {t("holdingsTable.columns.gainPct")}{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.price")}</th>
            {!relativeViewEnabled && visibleColumns.cost && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("cost")}
              >
                {t("holdingsTable.columns.cost")}{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {showForward7d && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("forward_7d_change_pct")}
              >
                {t("holdingsTable.columns.forward7d")}
                {sortKey === "forward_7d_change_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            {showForward30d && (
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("forward_30d_change_pct")}
              >
                {t("holdingsTable.columns.forward30d")}
                {sortKey === "forward_30d_change_pct" ? (asc ? " ▲" : " ▼") : ""}
              </th>
            )}
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("weight_pct")}
            >
              {t("holdingsTable.columns.weightPct")}{sortKey === "weight_pct" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.trend}`}>
              {t("holdingsTable.trendHeader", { range: sparkRange })}
            </th>
            <th className={tableStyles.cell}>{t("instrumentTable.columns.ccy")}</th>
            <th className={tableStyles.cell}>{t("instrumentTable.columns.type")}</th>
            <th className={tableStyles.cell}>{t("holdingsTable.columns.acquired")}</th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("days_held")}
            >
              {t("holdingsTable.columns.daysHeld")}{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.center}`}>{t("holdingsTable.columns.stage")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.center}`}>{t("holdingsTable.columns.eligible")}</th>
          </tr>
        </thead>

        <tbody>
          {paddingTop > 0 && (
            <tr style={{ height: paddingTop }}>
              <td
                colSpan={21 + (showAccount ? 1 : 0) + (showForward7d ? 1 : 0) + (showForward30d ? 1 : 0)}
                className="p-0 border-0"
              />
            </tr>
          )}
          {items.map((virtualRow) => {
            const h = sortedRows[virtualRow.index];
            const handleSelect = () => {
              onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
            };
            const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              event.stopPropagation();
              handleSelect();
            };
            return (
              <tr
                key={h.row_key ?? h.ticker + h.acquired_date}
                onClick={onSelectInstrument ? handleSelect : undefined}
                className={onSelectInstrument ? tableStyles.clickable : undefined}
              >
                {showAccount && (
                  <td className={tableStyles.cell}>{h.source_account}</td>
                )}
                <td className={tableStyles.cell}>
                  <button
                    type="button"
                    onClick={handleClick}
                    className="link-button focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
                  >
                    {h.ticker}
                  </button>
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.name}`}>{h.name}</td>
                {!relativeViewEnabled && visibleColumns.units && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {new Intl.NumberFormat(i18n.language).format(h.units ?? 0)}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.market && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {money(h.market, h.market_value_currency || baseCurrency)}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.gain && (
                  <td className={`${tableStyles.cell} ${tableStyles.right} ${getPerformanceClass(h.gain)}`}>
                    {money(h.gain, h.gain_currency || baseCurrency)}
                  </td>
                )}
                {visibleColumns.gain_pct && (
                  <td className={`${tableStyles.cell} ${tableStyles.right} ${getPerformanceClass(h.gain_pct)}`}>
                    {percent(h.gain_pct, 1)}
                  </td>
                )}
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  <span className={h.is_stale ? "text-gray" : undefined}>
                    {money(
                      h.current_price_gbp,
                      h.current_price_currency || baseCurrency,
                    )}
                  </span>
                  {h.is_stale && (
                    <span
                      className="ml-1 text-warning"
                      title={h.last_price_time ?? undefined}
                    >
                      *
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
                {!relativeViewEnabled && visibleColumns.cost && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right}`}
                    title={(h.cost_basis_gbp ?? 0) > 0 ? t("holdingsTable.actualPurchaseCost") : t("holdingsTable.inferredCost")}
                  >
                    {money(
                      h.cost,
                      h.cost_basis_currency ||
                        h.effective_cost_basis_currency ||
                        baseCurrency,
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
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {percent(h.weight_pct ?? 0, 1)}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.trend}`}>
                  <Sparkline
                    ticker={h.ticker}
                    days={sparkRange}
                    width={80}
                    ariaLabel={t("holdingsTable.sparklineAria", { ticker: h.ticker })}
                  />
                </td>
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
                <td className={tableStyles.cell}>
                  {translateInstrumentType(t, h.instrument_type)}
                </td>
                <td className={tableStyles.cell}>
                  {h.acquired_date && !isNaN(Date.parse(h.acquired_date))
                    ? formatDateISO(new Date(h.acquired_date))
                    : "—"}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {h.days_held ?? "—"}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.center}`}>
                  {(() => {
                    const stage = getGrowthStage({ daysHeld: h.days_held });
                    return <span title={stage.message}>{stage.icon}</span>;
                  })()}
                </td>
                <td
                  className={`${tableStyles.cell} ${tableStyles.center} ${h.sell_eligible ? 'text-positive' : 'text-warning'}`}
                  title={
                    h.next_eligible_sell_date
                      ? formatDateISO(new Date(h.next_eligible_sell_date))
                      : undefined
                  }
                >
                  {h.sell_eligible
                    ? `✓ ${t("holdingsTable.eligible")}`
                    : `✗ ${h.days_until_eligible ?? ""}`}
                </td>
              </tr>
            );
          })}
          {paddingBottom > 0 && (
            <tr style={{ height: paddingBottom }}>
              <td
                colSpan={21 + (showAccount ? 1 : 0) + (showForward7d ? 1 : 0) + (showForward30d ? 1 : 0)}
                className="p-0 border-0"
              />
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <td className={`${tableStyles.cell} font-semibold`} colSpan={showAccount ? 3 : 2}>
              {t("holdingsTable.totalRowLabel")}
            </td>
            {!relativeViewEnabled && visibleColumns.units && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {!relativeViewEnabled && visibleColumns.market && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {money(totals.market, baseCurrency)}
              </td>
            )}
            {!relativeViewEnabled && visibleColumns.gain && (
              <td
                className={`${tableStyles.cell} ${tableStyles.right} font-semibold ${getPerformanceClass(totals.gain)}`}
              >
                {money(totals.gain, baseCurrency)}
              </td>
            )}
            {visibleColumns.gain_pct && (
              <td
                className={`${tableStyles.cell} ${tableStyles.right} font-semibold ${getPerformanceClass(totalGainPct)}`}
              >
                {percent(totalGainPct, 1)}
              </td>
            )}
            <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            {!relativeViewEnabled && visibleColumns.cost && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
                {money(totals.cost, baseCurrency)}
              </td>
            )}
            {showForward7d && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            {showForward30d && (
              <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>—</td>
            )}
            <td className={`${tableStyles.cell} ${tableStyles.right} font-semibold`}>
              {percent(totals.weight, 1)}
            </td>
            {Array.from({ length: 7 }, (_, index) => (
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
