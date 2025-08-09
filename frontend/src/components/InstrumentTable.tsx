import { useState } from "react";
import type { InstrumentSummary } from "../types";
import { InstrumentDetail } from "./InstrumentDetail";
import { money } from "../lib/money";

type Props = {
    rows: InstrumentSummary[];
};

export function InstrumentTable({ rows }: Props) {
    const [selected, setSelected] = useState<InstrumentSummary | null>(null);

    /* no data? – render a clear message instead of an empty table */
    if (!rows.length) {
        return <p>No instruments found for this group.</p>;
    }

    /* simple cell styles */
    const cell = { padding: "4px 6px" } as const;
    const right = { ...cell, textAlign: "right" } as const;

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
                        <th style={cell}>Ticker</th>
                        <th style={cell}>Name</th>
                        <th style={right}>Units</th>
                        <th style={right}>Mkt £</th>
                        <th style={right}>Gain £</th>
                        <th style={right}>Last £</th>
                        <th style={right}>Last&nbsp;Date</th>
                        <th style={right}>Δ&nbsp;7&nbsp;d&nbsp;%</th>
                        <th style={right}>Δ&nbsp;1&nbsp;mo&nbsp;%</th>
                    </tr>
                </thead>

                <tbody>
                    {rows.map((r) => {
                        const gainColour =
                            r.gain_gbp >= 0 ? "lightgreen" : "red";

                        return (
                            <tr
                                key={r.ticker}
                                onClick={() => setSelected(r)}
                            >
                                <td style={cell}>{r.ticker}</td>
                                <td style={cell}>{r.name}</td>
                                <td style={right}>
                                    {r.units.toLocaleString()}
                                </td>
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
                    onClose={() => setSelected(null)}
                />
            )}
        </>
    );
}
