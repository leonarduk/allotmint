import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { useFilterableTable } from "../hooks/useFilterableTable";
import { money, percent } from "../lib/money";
import tableStyles from "../styles/table.module.css";
import i18n from "../i18n";

type Props = {
    rows: InstrumentSummary[];
};

export function InstrumentTable({ rows }: Props) {
    const { t } = useTranslation();
    const [selected, setSelected] = useState<InstrumentSummary | null>(null);
    const [visibleColumns, setVisibleColumns] = useState({
        units: true,
        cost: true,
        market: true,
        gain: true,
        gain_pct: true,
    });

    const toggleColumn = (key: keyof typeof visibleColumns) => {
        setVisibleColumns((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const rowsWithCost = rows.map((r) => {
        const cost = r.market_value_gbp - r.gain_gbp;
        const gain_pct =
            r.gain_pct !== undefined && r.gain_pct !== null
                ? r.gain_pct
                : cost
                ? (r.gain_gbp / cost) * 100
                : 0;
        return { ...r, cost, gain_pct };
    });

    const { rows: sorted, sortKey, asc, handleSort } = useFilterableTable(
        rowsWithCost,
        "ticker",
        {},
    );

    /* no data? – render a clear message instead of an empty table */
    if (!rowsWithCost.length) {
        return <p>{t("instrumentTable.noInstruments")}</p>;
    }

    const columnLabels: [keyof typeof visibleColumns, string][] = [
        ["units", "Units"],
        ["cost", "Cost"],
        ["market", "Market"],
        ["gain", "Gain"],
        ["gain_pct", "Gain %"],
    ];

    return (
        <>
            <div style={{ marginBottom: "0.5rem" }}>
                Columns:
                {columnLabels.map(([key, label]) => (
                    <label key={key} style={{ marginLeft: "0.5rem" }}>
                        <input
                            type="checkbox"
                            checked={visibleColumns[key]}
                            onChange={() => toggleColumn(key)}
                        />
                        {label}
                    </label>
                ))}
            </div>
            <table
                className={`${tableStyles.table} ${tableStyles.clickable}`}
                style={{ marginBottom: "1rem" }}
            >
                <thead>
                    <tr>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.clickable}`}
                            onClick={() => handleSort("ticker")}
                        >
                            {t("instrumentTable.columns.ticker")}
                            {sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.clickable}`}
                            onClick={() => handleSort("name")}
                        >
                            {t("instrumentTable.columns.name")}
                            {sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={tableStyles.cell}>{t("instrumentTable.columns.ccy")}</th>
                        <th className={tableStyles.cell}>{t("instrumentTable.columns.type")}</th>
                        {visibleColumns.units && (
                            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.units")}</th>
                        )}
                        {visibleColumns.cost && (
                            <th
                                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                                onClick={() => handleSort("cost")}
                            >
                                {t("instrumentTable.columns.cost")}
                                {sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
                            </th>
                        )}
                        {visibleColumns.market && (
                            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.market")}</th>
                        )}
                        {visibleColumns.gain && (
                            <th
                                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                                onClick={() => handleSort("gain")}
                            >
                                {t("instrumentTable.columns.gain")}
                                {sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
                            </th>
                        )}
                        {visibleColumns.gain_pct && (
                            <th
                                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                                onClick={() => handleSort("gain_pct")}
                            >
                                {t("instrumentTable.columns.gainPct")}
                                {sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
                            </th>
                        )}
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.last")}</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.lastDate")}</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.delta7d")}</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("instrumentTable.columns.delta30d")}</th>
                    </tr>
                </thead>

                <tbody>
                    {sorted.map((r) => {
                        const gainColour = r.gain_gbp >= 0 ? "lightgreen" : "red";

                        return (
                            <tr key={r.ticker}>
                                <td className={tableStyles.cell}>
                                    <button
                                        type="button"
                                        onClick={() => setSelected(r)}
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
                                        {r.ticker}
                                    </button>
                                </td>
                                <td className={tableStyles.cell}>{r.name}</td>
                                <td className={tableStyles.cell}>{r.currency ?? "—"}</td>
                                <td className={tableStyles.cell}>{r.instrument_type ?? "—"}</td>
                                {visibleColumns.units && (
                                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                        {new Intl.NumberFormat(i18n.language).format(r.units)}
                                    </td>
                                )}
                                {visibleColumns.cost && (
                                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(r.cost)}</td>
                                )}
                                {visibleColumns.market && (
                                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(r.market_value_gbp)}</td>
                                )}
                                {visibleColumns.gain && (
                                    <td className={`${tableStyles.cell} ${tableStyles.right}`} style={{ color: gainColour }}>
                                        {money(r.gain_gbp)}
                                    </td>
                                )}
                                {visibleColumns.gain_pct && (
                                    <td
                                        className={`${tableStyles.cell} ${tableStyles.right}`}
                                        style={{ color: r.gain_pct >= 0 ? "lightgreen" : "red" }}
                                    >
                                        {percent(r.gain_pct, 1)}
                                    </td>
                                )}
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.last_price_gbp != null ? money(r.last_price_gbp) : "—"}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.last_price_date
                                        ? new Intl.DateTimeFormat(i18n.language).format(
                                              new Date(r.last_price_date),
                                          )
                                        : "—"}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.change_7d_pct == null ? "—" : percent(r.change_7d_pct, 1)}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.change_30d_pct == null ? "—" : percent(r.change_30d_pct, 1)}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>

            {/* slide-in price-history / positions panel */}
            {selected && (
                <InstrumentDetail
                    ticker={selected.ticker}
                    name={selected.name}
                    currency={selected.currency}
                    instrument_type={selected.instrument_type}
                    onClose={() => setSelected(null)}
                />
            )}
        </>
    );
}

