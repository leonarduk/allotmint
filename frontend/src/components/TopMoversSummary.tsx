import { useCallback, useEffect, useMemo, useState } from "react";
import type { MoverRow, TradingSignal } from "../types";
import { getGroupMovers, getTradingSignals } from "../api";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { SignalBadge } from "./SignalBadge";
import { InstrumentDetail } from "./InstrumentDetail";

interface Props {
  slug?: string;
  days?: number;
  limit?: number;
}

export function TopMoversSummary({ slug, days = 1, limit = 5 }: Props) {
  const fetchMovers = useCallback(() => {
    if (!slug) return Promise.resolve({ gainers: [], losers: [] });
    return getGroupMovers(slug, days, limit, 0);
  }, [slug, days, limit]);
  const { data, loading, error } = useFetch(fetchMovers, [slug, days, limit], !!slug);

  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [selected, setSelected] = useState<{ ticker: string; name: string } | null>(
    null,
  );

  useEffect(() => {
    if (!slug) return;
    getTradingSignals()
      .then(setSignals)
      .catch((e) => console.error(e));
  }, [slug]);

  const signalMap = useMemo(() => {
    const map = new Map<string, TradingSignal>();
    for (const s of signals ?? []) map.set(s.ticker, s);
    return map;
  }, [signals]);

  if (!slug || loading || error || !data) return null;

  const rows = [...data.gainers, ...data.losers];
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
                      onClick={() =>
                        setSelected({ ticker: r.ticker, name: r.name })
                      }
                    />
                  ) : null;
                })()}
              </td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: r.change_pct >= 0 ? "green" : "red" }}
              >
                {r.change_pct.toFixed(2)}
<!-- =======
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
<!--         <tbody>
//           {rows.map((row) => (
<!--             <tr key={row.ticker}>
              <td className={tableStyles.cell}>{row.name}</td>
              <td
                className={`${tableStyles.cell} ${tableStyles.right}`}
                style={{ color: row.change_pct >= 0 ? "lightgreen" : "red" }}
              >
<!--                 {percent(row.change_pct)} --> --> --> -->
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
<!-- =======
      <div style={{ textAlign: "right", marginTop: "0.5rem" }}>
        <Link to={moversPlugin.path({ group: slug })}>View more</Link>
      </div>
    </div>
  );
}
 -->
export default TopMoversSummary;

