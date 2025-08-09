import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";

type Props = {
    rows: InstrumentSummary[];
};

export function InstrumentTable({ rows }: Props) {
    const [selected, setSelected] = useState<InstrumentSummary | null>(null);

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

    const { sorted, sortKey, asc, handleSort } = useSortableTable(rowsWithCost, "ticker");

    /* no data? – render a clear message instead of an empty table */
    if (!rowsWithCost.length) {
        return <p>No instruments found for this group.</p>;
    }

    return (
        <>
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
                            Ticker
                            {sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.clickable}`}
                            onClick={() => handleSort("name")}
                        >
                            Name
                            {sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={tableStyles.cell}>CCY</th>
                        <th className={tableStyles.cell}>Type</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Units</th>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                            onClick={() => handleSort("cost")}
                        >
                            Cost £
                            {sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Mkt £</th>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                            onClick={() => handleSort("gain")}
                        >
                            Gain £
                            {sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                            onClick={() => handleSort("gain_pct")}
                        >
                            Gain %
                            {sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Last £</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Last&nbsp;Date</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ&nbsp;7&nbsp;d&nbsp;%</th>
                        <th className={`${tableStyles.cell} ${tableStyles.right}`}>Δ&nbsp;1&nbsp;mo&nbsp;%</th>
                    </tr>
                </thead>

                <tbody>
                    {sorted.map((r) => {
                        const gainColour =
                            r.gain_gbp >= 0 ? "lightgreen" : "red";

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
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.units.toLocaleString()}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{money(r.cost)}</td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {money(r.market_value_gbp)}
                                </td>
                                <td
                                    className={`${tableStyles.cell} ${tableStyles.right}`}
                                    style={{ color: gainColour }}
                                >
                                    {money(r.gain_gbp)}
                                </td>
                                <td
                                    className={`${tableStyles.cell} ${tableStyles.right}`}
                                    style={{ color: r.gain_pct >= 0 ? "lightgreen" : "red" }}
                                >
                                    {Number.isFinite(r.gain_pct) ? r.gain_pct.toFixed(1) : "—"}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.last_price_gbp != null
                                        ? money(r.last_price_gbp)
                                        : "—"}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.last_price_date ?? "—"}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.change_7d_pct == null
                                        ? "—"
                                        : r.change_7d_pct.toFixed(1)}
                                </td>
                                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                                    {r.change_30d_pct == null
                                        ? "—"
                                        : r.change_30d_pct.toFixed(1)}
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
