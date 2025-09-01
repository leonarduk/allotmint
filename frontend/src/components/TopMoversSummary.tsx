import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import { getGroupMovers } from "../api";
import type { MoverRow } from "../types";
import { useFetch } from "../hooks/useFetch";
import { percent } from "../lib/money";
import tableStyles from "../styles/table.module.css";
import moversPlugin from "../plugins/movers";

interface Props {
  slug: string;
  limit?: number;
}

export function TopMoversSummary({ slug, limit = 5 }: Props) {
  const [retry, setRetry] = useState(0);
  const { data, loading, error } = useFetch<{
    gainers: MoverRow[];
    losers: MoverRow[];
  }>(() => getGroupMovers(slug, 1, limit), [slug, limit, retry], !!slug);

  const rows = useMemo(() => {
    if (!data || !Array.isArray(data.gainers) || !Array.isArray(data.losers))
      return [] as MoverRow[];
    return [...data.gainers, ...data.losers]
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, limit);
  }, [data, limit]);

  if (!slug) return null;
  if (loading)
    return (
      <div role="status" aria-busy="true">
        Loading movers…
      </div>
    );
  if (error)
    return (
      <div style={{ color: "red" }}>
        <p>Failed to load movers</p>
        <button onClick={() => setRetry((r) => r + 1)}>Retry</button>
      </div>
    );
  if (!rows.length) return null;

  return (
    <div style={{ marginBottom: "1rem" }}>
      <h3>Top Movers</h3>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Name</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>Change %</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker}>
              <td className={tableStyles.cell}>{row.name}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.change_pct >= 0 ? "lightgreen" : "red" }}
              >
                {percent(row.change_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ textAlign: "right", marginTop: "0.5rem" }}>
        <Link to={moversPlugin.path({ group: slug })}>View more</Link>
      </div>
    </div>
  );
}

export default TopMoversSummary;
