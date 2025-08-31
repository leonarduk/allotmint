import { useState, useEffect, useRef , useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Holding, InstrumentDetailMini } from "../types";
import { money, percent } from "../lib/money";
import { translateInstrumentType } from "../lib/instrumentType";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";
import { useConfig } from "../ConfigContext";
import { isSupportedFx } from "../lib/fx";
import { useVirtualizer } from "@tanstack/react-virtual";
import { getInstrumentDetail } from "../api";
import { LineChart, Line, ResponsiveContainer } from "recharts";

const VIEW_PRESET_STORAGE_KEY = "holdingsTableViewPreset";

type Props = {
  holdings: Holding[];
  onSelectInstrument?: (ticker: string, name: string) => void;
};


export function HoldingsTable({
  holdings,
  onSelectInstrument,
}: Props) {
  const { t } = useTranslation();
  const { relativeViewEnabled } = useConfig();

  const viewPresets = useMemo(
    () => [
      { label: t("holdingsTable.viewPresets.all"), value: "" },
      { label: t("instrumentType.etf"), value: "ETF" },
      { label: t("instrumentType.equity"), value: "Equity" },
      { label: t("instrumentType.bond"), value: "Bond" },
    ],
    [t],
  );

  const [filters, setFilters] = useState({
    ticker: "",
    name: "",
    instrument_type: "",
    units: "",
    gain_pct: "",
    sell_eligible: "",
  });

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
  const [sparks, setSparks] = useState<Record<string, InstrumentDetailMini>>({});

  const toggleColumn = (key: keyof typeof visibleColumns) => {
    setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleFilterChange = (key: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  // Track tickers we've already fetched to avoid re-fetching on re-renders
  const fetchedTickersRef = useRef<Set<string>>(new Set());

  // Fetch sparkline data for new tickers whenever holdings change
  useEffect(() => {
    const tickers = Array.from(new Set(holdings.map((h) => h.ticker)));
    const toFetch = tickers.filter(
      (t) => !sparks[t] && !fetchedTickersRef.current.has(t),
    );

    toFetch.forEach((t) => {
      fetchedTickersRef.current.add(t);
      getInstrumentDetail(t, 180)
        .then((d) => {
          const m = d?.mini;
          if (m) {
            setSparks((prev) => ({ ...prev, [t]: m }));
          }
        })
        .catch(() => {});
    });
  }, [holdings, sparks]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(VIEW_PRESET_STORAGE_KEY, viewPreset);
    }
    setFilters((prev) => ({ ...prev, instrument_type: viewPreset }));
  }, [viewPreset]);

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

  const columnLabels: [keyof typeof visibleColumns, string][] = [
    ["units", t("holdingsTable.columns.units")],
    ["cost", t("holdingsTable.columns.cost")],
    ["market", t("holdingsTable.columns.market")],
    ["gain", t("holdingsTable.columns.gain")],
    ["gain_pct", t("holdingsTable.columns.gainPct")],
  ];

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const tableHeaderRef = useRef<HTMLTableSectionElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);

  useEffect(() => {
    if (tableHeaderRef.current) {
      setHeaderHeight(tableHeaderRef.current.getBoundingClientRect().height);
    }
  }, []);

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
            className={`ml-2 ${viewPreset === p.value ? 'font-bold' : ''}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="mb-2">
        {t("holdingsTable.quickFilters")}
        <button
          type="button"
          className="ml-2"
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
      {sortedRows.length ? (
        <div className="overflow-x-auto md:overflow-visible">
          <table className={`${tableStyles.table} mb-4 w-full`}>
        <thead ref={tableHeaderRef}>
          <tr>
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
            <th className={tableStyles.cell}></th>
            <th className={tableStyles.cell}></th>
            <th className={tableStyles.cell}>
              <input
                placeholder={t("holdingsTable.filters.type")}
                value={filters.instrument_type}
                onChange={(e) => handleFilterChange("instrument_type", e.target.value)}
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
            <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
            {!relativeViewEnabled && visibleColumns.cost && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
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
            <th className={tableStyles.cell}></th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
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
            <th className={`${tableStyles.cell} ${tableStyles.clickable}`} onClick={() => handleSort("ticker")}>
              {t("holdingsTable.columns.ticker")}{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.clickable}`} onClick={() => handleSort("name")}>
              {t("holdingsTable.columns.name")}{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={tableStyles.cell}>{t("holdingsTable.columns.trend")}</th>
            <th className={tableStyles.cell}>{t("instrumentTable.columns.ccy")}</th>
            <th className={tableStyles.cell}>{t("instrumentTable.columns.type")}</th>
            {!relativeViewEnabled && visibleColumns.units && (
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.units")}</th>
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
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("weight_pct")}
            >
              {t("holdingsTable.columns.weightPct")}{sortKey === "weight_pct" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={tableStyles.cell}>{t("holdingsTable.columns.acquired")}</th>
            <th
              className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
              onClick={() => handleSort("days_held")}
            >
              {t("holdingsTable.columns.daysHeld")}{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
            </th>
            <th className={`${tableStyles.cell} ${tableStyles.center}`}>{t("holdingsTable.columns.eligible")}</th>
          </tr>
        </thead>

        <tbody>
          {paddingTop > 0 && (
            <tr style={{ height: paddingTop }}>
              <td colSpan={20} className="p-0 border-0" />
            </tr>
          )}
          {items.map((virtualRow) => {
            const h = sortedRows[virtualRow.index];
            const handleClick = () =>
              onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
            return (
              <tr key={h.ticker + h.acquired_date}>
                <td className={tableStyles.cell}>
                  <button
                    type="button"
                    onClick={handleClick}
                    className="link-button"
                  >
                    {h.ticker}
                  </button>
                </td>
                <td className={tableStyles.cell}>{h.name}</td>
                <td className={`${tableStyles.cell} w-20`}>
                  {sparks[h.ticker]?.[String(sparkRange)]?.length ? (
                    <ResponsiveContainer width="100%" height={40}>
                      <LineChart data={sparks[h.ticker][String(sparkRange)]} margin={{ left: 0, right: 0, top: 0, bottom: 0 }}>
                        <Line type="monotone" dataKey="close_gbp" stroke="#8884d8" dot={false} strokeWidth={1} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : null}
                </td>
                <td className={tableStyles.cell}>
                  {isSupportedFx(h.currency) ? (
                    <button
                      type="button"
                      onClick={() =>
                        onSelectInstrument?.(`${h.currency!}GBP.FX`, h.currency!)
                      }
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
                {!relativeViewEnabled && visibleColumns.units && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {new Intl.NumberFormat(i18n.language).format(h.units ?? 0)}
                  </td>
                )}
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {money(h.current_price_gbp)}
                  {h.last_price_date && (
                    <span
                      className={tableStyles.badge}
                      title={h.last_price_date}
                    >
                      {new Intl.DateTimeFormat(i18n.language).format(
                        new Date(h.last_price_date),
                      )}
                    </span>
                  )}
                  {h.latest_source && (
                    <span className="ml-1 text-gray">
                      {t("holdingsTable.source")} {h.latest_source}
                    </span>
                  )}
                </td>
                {!relativeViewEnabled && visibleColumns.cost && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right}`}
                    title={(h.cost_basis_gbp ?? 0) > 0 ? t("holdingsTable.actualPurchaseCost") : t("holdingsTable.inferredCost")}
                  >
                    {money(h.cost)}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.market && (
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {money(h.market)}
                  </td>
                )}
                {!relativeViewEnabled && visibleColumns.gain && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${(h.gain ?? 0) >= 0 ? 'text-positive' : 'text-negative'}`}
                  >
                    {money(h.gain)}
                  </td>
                )}
                {visibleColumns.gain_pct && (
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${(h.gain_pct ?? 0) >= 0 ? 'text-positive' : 'text-negative'}`}
                  >
                    {percent(h.gain_pct ?? 0, 1)}
                  </td>
                )}
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {percent(h.weight_pct ?? 0, 1)}
                </td>
                <td className={tableStyles.cell}>
                  {h.acquired_date && !isNaN(Date.parse(h.acquired_date))
                    ? new Intl.DateTimeFormat(i18n.language).format(
                        new Date(h.acquired_date),
                      )
                    : "—"}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {h.days_held ?? "—"}
                </td>
                <td
                  className={`${tableStyles.cell} ${tableStyles.center} ${h.sell_eligible ? 'text-positive' : 'text-warning'}`}
                  title={
                    h.next_eligible_sell_date
                      ? new Intl.DateTimeFormat(i18n.language).format(
                          new Date(h.next_eligible_sell_date)
                        )
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
              <td colSpan={20} className="p-0 border-0" />
            </tr>
          )}
        </tbody>
        </table>
        </div>
      ) : (
        <p>{t("holdingsTable.noHoldings")}</p>
      )}
    </>
  );
}

