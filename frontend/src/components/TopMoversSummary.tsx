import { Link } from "react-router-dom";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { MoverRow, TradingSignal } from "../types";
import { getGroupMovers, getTradingSignals } from "../api";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import moversPlugin from "../plugins/movers";
import { SignalBadge } from "./SignalBadge";
import { InstrumentDetail } from "./InstrumentDetail";

interface Props {
  slug?: string;
  days?: number;
  limit?: number;
}

export function TopMoversSummary({ slug, days = 1, limit = 5 }: Props) {
  const fetchMovers = useCallback(async () => {
    if (!slug) return { gainers: [], losers: [] };
    try {
      return await getGroupMovers(slug, days, limit, 0);
    } catch (e) {
      console.error(e);
      return { gainers: [], losers: [] };
    }
  }, [slug, days, limit]);
  const { data, loading, error } = useFetch(fetchMovers, [slug, days, limit], !!slug);

  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [selected, setSelected] = useState<{ ticker: string; name: string } | null>(null);

  useEffect(() => {
    if (!slug) return;
    getTradingSignals()
      .then(setSignals)
      .catch((e) => {
        console.error(e);
        setSignals([]);
      });
  }, [slug]);

  const signalMap = useMemo(() => {
    const map = new Map<string, TradingSignal>();
    for (const s of signals ?? []) map.set(s.ticker, s);
    return map;
  }, [signals]);

  const rows = useMemo(() => {
    if (!data || !Array.isArray(data.gainers) || !Array.isArray(data.losers))
      return [];
    return [...data.gainers, ...data.losers]
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, limit);
  }, [data, limit]);

  if (!slug) return <div>No group selected.</div>;
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
          {rows.map((r: MoverRow) => (
            <tr key={r.ticker}>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={() => setSelected({ ticker: r.ticker, name: r.name })}
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
                {(() => {
                  const s = signalMap.get(r.ticker);
                  return s ? (
                    <SignalBadge
                      action={s.action}
                      reason={s.reason}
                      confidence={s.confidence}
                      rationale={s.rationale}
                      onClick={() => setSelected({ ticker: r.ticker, name: r.name })}
                    />
                  ) : null;
                })()}
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
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

export default TopMoversSummary;
