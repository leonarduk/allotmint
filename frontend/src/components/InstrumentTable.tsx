import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";
import styles from "../styles/table.module.css";
import { useSortableTable } from "../hooks/useSortableTable";

type SortKey = "ticker" | "name" | "cost" | "gain" | "gain_pct";

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

    const { sorted, sortKey, asc, handleSort } = useSortableTable<
        (typeof rowsWithCost)[number],
        SortKey
    >(rowsWithCost, "ticker");

    /* no data? – render a clear message instead of an empty table */
    if (!rowsWithCost.length) {
        return <p>No instruments found for this group.</p>;
    }

    return (
        <>
            <table className={`${styles.table} ${styles.clickable}`}>
                <thead>
                    <tr>
                        <th
                            className={`${styles.cell} ${styles.clickable}`}
                            onClick={() => handleSort("ticker")}
                        >
                            Ticker
                            {sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            className={`${styles.cell} ${styles.clickable}`}
                            onClick={() => handleSort("name")}
                        >
                            Name
                            {sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={styles.cell}>CCY</th>
                        <th className={styles.cell}>Type</th>
                        <th className={`${styles.cell} ${styles.right}`}>Units</th>
                        <th className={styles.cell}>CCY</th>
                        <th
                            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
                            onClick={() => handleSort("cost")}
                        >
                            Cost £
                            {sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={`${styles.cell} ${styles.right}`}>Mkt £</th>
                        <th
                            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
                            onClick={() => handleSort("gain")}
                        >
                            Gain £
                            {sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
                            onClick={() => handleSort("gain_pct")}
                        >
                            Gain %
                            {sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th className={`${styles.cell} ${styles.right}`}>Last £</th>
                        <th className={`${styles.cell} ${styles.right}`}>Last&nbsp;Date</th>
                        <th className={`${styles.cell} ${styles.right}`}>Δ&nbsp;7&nbsp;d&nbsp;%</th>
                        <th className={`${styles.cell} ${styles.right}`}>Δ&nbsp;1&nbsp;mo&nbsp;%</th>
                    </tr>
                </thead>

                <tbody>
                    {sorted.map((r) => {
                        const gainColour =
                            r.gain_gbp >= 0 ? "lightgreen" : "red";

                        return (
                            <tr key={r.ticker}>
                                <td className={styles.cell}>
                                    <a
                                        href="#"
                                        onClick={(e) => {
                                            e.preventDefault();
                                            setSelected(r);
                                        }}
                                        className={styles.link}
                                    >
                                        {r.ticker}
                                    </a>
                                </td>
                                <td className={styles.cell}>{r.name}</td>
                                <td className={styles.cell}>{r.currency ?? "—"}</td>
                                <td className={styles.cell}>{r.instrument_type ?? "—"}</td>
                                <td className={`${styles.cell} ${styles.right}`}>
                                    {r.units.toLocaleString()}
                                </td>
                                <td className={`${styles.cell} ${styles.right}`}>{money(r.cost)}</td>
                                <td className={`${styles.cell} ${styles.right}`}>
                                    {money(r.market_value_gbp)}
                                </td>
                                <td
                                    className={`${styles.cell} ${styles.right}`}
                                    style={{ color: gainColour }}
                                >
                                    {money(r.gain_gbp)}
                                </td>
                                <td
                                    className={`${styles.cell} ${styles.right}`}
                                    style={{ color: r.gain_pct >= 0 ? "lightgreen" : "red" }}
                                >
                                    {Number.isFinite(r.gain_pct) ? r.gain_pct.toFixed(1) : "—"}
                                </td>
                                <td className={`${styles.cell} ${styles.right}`}>
                                    {r.last_price_gbp != null
                                        ? money(r.last_price_gbp)
                                        : "—"}
                                </td>
                                <td className={`${styles.cell} ${styles.right}`}>
                                    {r.last_price_date ?? "—"}
                                </td>
                                <td className={`${styles.cell} ${styles.right}`}>
                                    {r.change_7d_pct == null
                                        ? "—"
                                        : r.change_7d_pct.toFixed(1)}
                                </td>
                                <td className={`${styles.cell} ${styles.right}`}>
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
