import { Link } from "react-router-dom";
import { useCallback, useMemo, useState } from "react";
import type { OpportunityEntry } from "../types";
import { getOpportunities } from "../api";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import moversPlugin from "../plugins/movers";
import { SignalBadge } from "./SignalBadge";
import { InstrumentDetail } from "./InstrumentDetail";
import EmptyState from "./EmptyState";

interface Props {
  slug?: string;
  days?: number;
  limit?: number;
}

export function TopMoversSummary({ slug, days = 1, limit = 5 }: Props) {
  const fetchOpportunities = useCallback(async () => {
    if (!slug) return null;
    try {
      return await getOpportunities({ group: slug, days, limit });
    } catch (e) {
      console.error(e);
      return null;
    }
  }, [slug, days, limit]);
  const { data, loading, error } = useFetch(
    fetchOpportunities,
    [slug, days, limit],
    !!slug,
  );

  const [selected, setSelected] = useState<{ ticker: string; name: string; signal?: OpportunityEntry['signal'] } | null>(null);

  const rows = useMemo(() => {
    if (!data || !Array.isArray(data.entries)) return [];
    return [...data.entries]
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, limit);
  }, [data, limit]);

  if (!slug) return <EmptyState message="No group selected." />;
  if (loading) return <div>Loading...</div>;
  if (error) return <div>Failed to load movers.</div>;
  if (rows.length === 0) return null;

  return (
    <>
      <table className={tableStyles.table} style={{ marginTop: "1rem" }}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Ticker</th>
            <th className={tableStyles.cell}>Name</th>
            <th className={tableStyles.cell}>Signal</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r: OpportunityEntry) => (
            <tr key={r.ticker}>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={() =>
                    setSelected({ ticker: r.ticker, name: r.name, signal: r.signal ?? undefined })
                  }
                  style={{
                    color: "dodgerblue",
                    textDecoration: "underline",
                    background: "none",
                    border: "none",
                    padding: 0,
                    font: "inherit",
                    cursor: "pointer",
                  }}
                  className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
                >
                  {r.ticker}
                </button>
              </td>
              <td className={tableStyles.cell}>{r.name}</td>
              <td className={tableStyles.cell}>
                {r.signal ? (
                  <SignalBadge
                    action={r.signal.action}
                    reason={r.signal.reason}
                    confidence={r.signal.confidence}
                    rationale={r.signal.rationale}
                    onClick={() =>
                      setSelected({ ticker: r.ticker, name: r.name, signal: r.signal ?? undefined })
                    }
                  />
                ) : null}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: r.change_pct >= 0 ? "green" : "red" }}
              >
                {r.change_pct.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ textAlign: "right", marginTop: "0.5rem" }}>
        <Link to={moversPlugin.path({ group: slug })}>View more</Link>
      </div>
      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name}
          signal={selected.signal ?? undefined}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

export default TopMoversSummary;
