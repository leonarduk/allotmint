import type { Holding } from "../types";

type Props = { holdings: Holding[] };

/**
 * Named export ― matches
 *   import { HoldingsTable } from "./HoldingsTable";
 * in AccountBlock.tsx.
 */
export function HoldingsTable({ holdings }: Props) {
    if (!holdings.length) return null;

    const cell  = { padding: "4px 6px" } as const;
    const right = { ...cell, textAlign: "right" } as const;

    return (
        <table
            style={{
                width: "100%",
                borderCollapse: "collapse",
                marginBottom: "1rem",
            }}
        >
            <thead>
                <tr>
                    <th style={cell}>Ticker</th>
                    <th style={cell}>Name</th>
                    <th style={right}>Units</th>
                    <th style={right}>Px £</th>
                    <th style={right}>Cost £</th>
                    <th style={right}>Mkt £</th>
                    <th style={right}>Gain £</th>
                    <th style={cell}>Acquired</th>
                    <th style={right}>Days&nbsp;Held</th>
                    <th style={{ ...cell, textAlign: "center" }}>Eligible?</th>
                </tr>
            </thead>

            <tbody>
                {holdings.map((h) => {
                    const cost =
                        (h.cost_basis_gbp ?? 0) > 0
                            ? h.cost_basis_gbp ?? 0
                            : h.effective_cost_basis_gbp ?? 0;

                    const market = h.market_value_gbp ?? 0;
                    const gain   = h.gain_gbp ?? market - cost;

                    return (
                        <tr key={h.ticker + h.acquired_date}>
                            <td style={cell}>
                                <a href={`/instrument/${encodeURIComponent(h.ticker)}`}>
                                    {h.ticker}
                                </a>
                            </td>
                            <td style={cell}>{h.name}</td>
                            <td style={right}>{h.units.toLocaleString()}</td>
                            <td style={right}>{(h.current_price_gbp ?? 0).toFixed(2)}</td>

                            <td
                                style={right}
                                title={
                                    (h.cost_basis_gbp ?? 0) > 0
                                        ? "Actual purchase cost"
                                        : "Inferred from price on acquisition date"
                                }
                            >
                                {cost.toFixed(2)}
                            </td>

                            <td style={right}>{market.toFixed(2)}</td>

                            <td
                                style={{
                                    ...right,
                                    color: gain >= 0 ? "lightgreen" : "red",
                                }}
                            >
                                {gain.toFixed(2)}
                            </td>

                            <td style={cell}>{h.acquired_date}</td>
                            <td style={right}>{h.days_held ?? "—"}</td>

                            <td
                                style={{
                                    ...cell,
                                    textAlign: "center",
                                    color: h.sell_eligible ? "lightgreen" : "gold",
                                }}
                            >
                                {h.sell_eligible
                                    ? "✓ Eligible"
                                    : `✗ ${h.days_until_eligible ?? ""}`}
                            </td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}
