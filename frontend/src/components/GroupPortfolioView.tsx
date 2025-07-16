import React from "react";
import type { GroupPortfolio } from "../types";

type Props = {
  data: GroupPortfolio | null;
  loading?: boolean;
  error?: string | null;
  onSelectMember?: (owner: string) => void; // to jump into owner view
};

export function GroupPortfolioView({ data, loading, error, onSelectMember }: Props) {
  if (loading) return <div>Loading group…</div>;
  if (error) return <div style={{ color: "red" }}>{error}</div>;
  if (!data) return <div>Select a group.</div>;

  const subt = data.subtotals_by_account_type || {};
  const acctTypes = Object.keys(subt).sort();

  return (
    <div>
      <h1 style={{ marginTop: 0, textTransform: "capitalize" }}>Group: {data.group}</h1>
      <div style={{ marginBottom: "1rem" }}>As of {data.as_of}</div>
      <div style={{ marginBottom: "1rem" }}>
        Approx Total: £{data.total_value_estimate_gbp.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>

      {acctTypes.length > 0 && (
        <div style={{ marginBottom: "2rem" }}>
          <h3>By Account Type</h3>
          <ul>
            {acctTypes.map((t) => (
              <li key={t}>
                {t}: £{subt[t].toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </li>
            ))}
          </ul>
        </div>
      )}

      <h3>Members</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "2rem" }}>
        <thead>
          <tr>
            <th style={th}>Owner</th>
            <th style={th}>Value £</th>
            <th style={th}>Trades / 20</th>
          </tr>
        </thead>
        <tbody>
          {data.members_summary.map((m) => (
            <tr
              key={m.owner}
              style={tr}
              onClick={() => onSelectMember?.(m.owner)}
            >
              <td style={tdLink}>{m.owner}</td>
              <td style={td}>{m.total_value_estimate_gbp.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              <td style={td}>{m.trades_this_month} ({m.trades_remaining} left)</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: "0.8rem", color: "#666" }}>
        Click a member to view their portfolio.
      </div>
    </div>
  );
}

const th: React.CSSProperties = { textAlign: "left", borderBottom: "1px solid #ccc", padding: "4px" };
const td: React.CSSProperties = { padding: "4px", borderBottom: "1px solid #eee" };
const tdLink: React.CSSProperties = { ...td, cursor: "pointer", textDecoration: "underline", color: "#0077cc" };
const tr: React.CSSProperties = {};
