import type React from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Holding } from "../types";
import { money, percent } from "../lib/money";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";

type Props = {
  holdings: Holding[];
  onSelectInstrument?: (ticker: string, name: string) => void;
  relativeView?: boolean;
};

export function HoldingsTable({
  holdings,
  onSelectInstrument,
  relativeView = false,
}: Props) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState({
    ticker: "",
    name: "",
    instrument_type: "",
    units: "",
    gain_pct: "",
    sell_eligible: "",
  });

  const handleFilterChange = (key: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

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

  if (!sortedRows.length) return null;

  return (
    <table className={tableStyles.table} style={{ marginBottom: "1rem" }}>
      <thead>
        <tr>
          <th className={tableStyles.cell}>
            <input
              placeholder={t("holdingsTable.columns.ticker")}
              value={filters.ticker}
              onChange={(e) => handleFilterChange("ticker", e.target.value)}
            />
          </th>
          <th className={tableStyles.cell}>
            <input
              placeholder={t("holdingsTable.columns.name")}
              value={filters.name}
              onChange={(e) => handleFilterChange("name", e.target.value)}
            />
          </th>
          <th className={tableStyles.cell}></th>
          <th className={tableStyles.cell}>
            <input
              placeholder={t("holdingsTable.columns.type")}
              value={filters.instrument_type}
              onChange={(e) => handleFilterChange("instrument_type", e.target.value)}
            />
          </th>
          {!relativeView && (
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>
              <input
                placeholder={t("holdingsTable.columns.units")}
                value={filters.units}
                onChange={(e) => handleFilterChange("units", e.target.value)}
              />
            </th>
          )}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
          {!relativeView && <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
          {!relativeView && <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>
            <input
              placeholder={t("holdingsTable.columns.gainPct")}
              value={filters.gain_pct}
              onChange={(e) => handleFilterChange("gain_pct", e.target.value)}
            />
          </th>
          <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
          <th className={tableStyles.cell}></th>
          <th className={`${tableStyles.cell} ${tableStyles.right}`}></th>
          <th className={`${tableStyles.cell} ${tableStyles.center}`}>
            <select
              aria-label={t("holdingsTable.filters.sellEligible")}
              value={filters.sell_eligible}
              onChange={(e) => handleFilterChange("sell_eligible", e.target.value)}
            >
              <option value="">{t("holdingsTable.options.all")}</option>
              <option value="true">{t("holdingsTable.options.yes")}</option>
              <option value="false">{t("holdingsTable.options.no")}</option>
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
          <th className={tableStyles.cell}>CCY</th>
          <th className={tableStyles.cell}>{t("holdingsTable.columns.type")}</th>
          {!relativeView && <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("holdingsTable.columns.units")}</th>}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>Px £</th>
          {!relativeView && (
            <th className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`} onClick={() => handleSort("cost")}>
              Cost £{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
            </th>
          )}
          <th className={`${tableStyles.cell} ${tableStyles.right}`}>Mkt £</th>
          {!relativeView && (
            <th className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`} onClick={() => handleSort("gain")}>
              Gain £{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
            </th>
          )}
          <th className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`} onClick={() => handleSort("gain_pct")}>
            {t("holdingsTable.columns.gainPct")}{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`} onClick={() => handleSort("weight_pct")}>
            Weight %{sortKey === "weight_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={tableStyles.cell}>Acquired</th>
          <th className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`} onClick={() => handleSort("days_held")}>
            Days&nbsp;Held{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${tableStyles.cell} ${tableStyles.center}`}>Eligible?</th>
        </tr>
      </thead>

      <tbody>
        {sortedRows.map((h) => {
          const handleClick = () => onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
          return (
            <tr key={h.ticker + h.acquired_date}>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={handleClick}
                  style={{
                    color: "dodgerblue",
                    textDecoration: "underline",
                    background: "none",
                    border: "none",
                    padding: 0,
                    font: "inherit",
                    cursor: "pointer",
                  }}
                >
                  {h.ticker}
                </button>
              </td>
              <td className={tableStyles.cell}>{h.name}</td>
              <td className={tableStyles.cell}>{h.currency ?? "—"}</td>
              <td className={tableStyles.cell}>{h.instrument_type ?? "—"}</td>
              {!relativeView && (
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {new Intl.NumberFormat(i18n.language).format(h.units ?? 0)}
                </td>
              )}
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(h.current_price_gbp)}</td>
              {!relativeView && (
                <td
                  className={`${tableStyles.cell} ${tableStyles.right}`}
                  title={(h.cost_basis_gbp ?? 0) > 0
                    ? t("holdingsTable.tooltips.actualCost")
                    : t("holdingsTable.tooltips.inferredCost")}
                >
                  {money(h.cost)}
                </td>
              )}
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(h.market)}</td>
              {!relativeView && (
                <td className={`${tableStyles.cell} ${tableStyles.right}`} style={{ color: (h.gain ?? 0) >= 0 ? "lightgreen" : "red" }}>
                  {money(h.gain)}
                </td>
              )}
              <td className={`${tableStyles.cell} ${tableStyles.right}`} style={{ color: (h.gain_pct ?? 0) >= 0 ? "lightgreen" : "red" }}>
                {percent(h.gain_pct ?? 0, 1)}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{percent(h.weight_pct ?? 0, 1)}</td>
              <td className={tableStyles.cell}>
                {h.acquired_date && !isNaN(Date.parse(h.acquired_date))
                  ? new Intl.DateTimeFormat(i18n.language).format(new Date(h.acquired_date))
                  : "—"}
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>{h.days_held ?? "—"}</td>
              <td className={`${tableStyles.cell} ${tableStyles.center}`} style={{ color: h.sell_eligible ? "lightgreen" : "gold" }}>
                {h.sell_eligible ? "✓ Eligible" : `✗ ${h.days_until_eligible ?? ""}`}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
