import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";

type SortKey = "ticker" | "name" | "cost" | "gain";

type Props = {
    rows: InstrumentSummary[];
};

export function InstrumentTable({ rows }: Props) {
    const [selected, setSelected] = useState<InstrumentSummary | null>(null);
    const [sortKey, setSortKey] = useState<SortKey>("ticker");
    const [asc, setAsc] = useState(true);

    /* no data? – render a clear message instead of an empty table */
    if (!rows.length) {
        return <p>No instruments found for this group.</p>;
    }

    /* simple cell styles */
    const cell = { padding: "4px 6px" } as const;
    const right = { ...cell, textAlign: "right" } as const;

    function handleSort(key: SortKey) {
        if (sortKey === key) {
            setAsc(!asc);
        } else {
            setSortKey(key);
            setAsc(true);
        }
    }

    const rowsWithCost = rows.map((r) => ({
        ...r,
        cost: r.market_value_gbp - r.gain_gbp,
    }));

    const sorted = [...rowsWithCost].sort((a, b) => {
        const va = a[sortKey as keyof typeof a];
        const vb = b[sortKey as keyof typeof b];
        if (typeof va === "string" && typeof vb === "string") {
            return asc ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        const na = (va as number) ?? 0;
        const nb = (vb as number) ?? 0;
        return asc ? na - nb : nb - na;
    });

    return (
        <>
            <table
                style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    cursor: "pointer",
                    marginBottom: "1rem",
                }}
            >
                <thead>
                    <tr>
                        <th
                            style={{ ...cell, cursor: "pointer" }}
                            onClick={() => handleSort("ticker")}
                        >
                            Ticker
                            {sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th
                            style={{ ...cell, cursor: "pointer" }}
                            onClick={() => handleSort("name")}
                        >
                            Name
                            {sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th style={cell}>CCY</th>
                        <th style={cell}>Type</th>
                        <th style={right}>Units</th>
                        <th
                            style={{ ...right, cursor: "pointer" }}
                            onClick={() => handleSort("cost")}
                        >
                            Cost £
                            {sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th style={right}>Mkt £</th>
                        <th
                            style={{ ...right, cursor: "pointer" }}
                            onClick={() => handleSort("gain")}
                        >
                            Gain £
                            {sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
                        </th>
                        <th style={right}>Last £</th>
                        <th style={right}>Last&nbsp;Date</th>
                        <th style={right}>Δ&nbsp;7&nbsp;d&nbsp;%</th>
                        <th style={right}>Δ&nbsp;1&nbsp;mo&nbsp;%</th>
                    </tr>
                </thead>

                <tbody>
                    {sorted.map((r) => {
                        const gainColour =
                            r.gain_gbp >= 0 ? "lightgreen" : "red";

                        return (
                            <tr
                                key={r.ticker}
                                onClick={() => setSelected(r)}
                            >
                                <td style={cell}>{r.ticker}</td>
                                <td style={cell}>{r.name}</td>
                                <td style={cell}>{r.currency ?? "—"}</td>
                                <td style={cell}>{r.instrument_type ?? "—"}</td>
                                <td style={right}>
                                    {r.units.toLocaleString()}
                                </td>
                                <td style={right}>{money(r.cost)}</td>
                                <td style={right}>
                                    {money(r.market_value_gbp)}
                                </td>
                                <td style={{ ...right, color: gainColour }}>
                                    {money(r.gain_gbp)}
                                </td>
                                <td style={right}>
                                    {r.last_price_gbp != null
                                        ? money(r.last_price_gbp)
                                        : "—"}
                                </td>
                                <td style={right}>
                                    {r.last_price_date ?? "—"}
                                </td>
                                <td style={right}>
                                    {r.change_7d_pct == null
                                        ? "—"
                                        : r.change_7d_pct.toFixed(1)}
                                </td>
                                <td style={right}>
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
