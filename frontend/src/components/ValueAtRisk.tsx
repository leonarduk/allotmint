import { useEffect, useState } from "react";
import {
  getValueAtRisk,
  recomputeValueAtRisk,
  getVarBreakdown,
} from "../api";
import VarBreakdownModal from "./VarBreakdownModal";
import type { VarBreakdown } from "../types";

interface Props {
  owner: string;
}

export function ValueAtRisk({ owner }: Props) {
  const [days, setDays] = useState<number>(30);
  const [var95, setVar95] = useState<number | null>(null);
  const [var99, setVar99] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [breakdown, setBreakdown] = useState<VarBreakdown[] | null>(null);

  useEffect(() => {
    if (!owner) return;
    let isMounted = true;
    setLoading(true);
    setErr(null);
    Promise.all([
      getValueAtRisk(owner, { days, confidence: 95 }),
      getValueAtRisk(owner, { days, confidence: 99 }),
    ])
      .then(([d95, d99]) => {
        if (!isMounted) return;
        const v95 = d95.length ? d95[d95.length - 1].var : null;
        const v99 = d99.length ? d99[d99.length - 1].var : null;
        setVar95(v95);
        setVar99(v99);
        if (v95 == null && v99 == null) {
          // attempt to refresh data on the backend
          recomputeValueAtRisk(owner, { days, confidence: 95 }).catch(() => {});
          recomputeValueAtRisk(owner, { days, confidence: 99 }).catch(() => {});
        }
      })
      .catch((e) => {
        if (isMounted)
          setErr(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [owner, days]);

  const format = (v: number | null) =>
    v != null
      ? `£${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : "–";

  return (
    <div style={{ marginBottom: "2rem" }}>
      <h2>Value at Risk</h2>
      <div style={{ marginBottom: "0.5rem" }}>
        <label style={{ fontSize: "0.85rem" }}>
          Period:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{ marginLeft: "0.25rem" }}
          >
            <option value={7}>1W</option>
            <option value={30}>1M</option>
            <option value={90}>3M</option>
            <option value={365}>1Y</option>
          </select>
        </label>
      </div>
      {loading && <div>Loading…</div>}
      {err && <div style={{ color: "red" }}>{err}</div>}
      {!loading && !err && var95 == null && var99 == null && (
        <div style={{ fontStyle: "italic", color: "#666" }}>
          No VaR data available.
        </div>
      )}
      {!loading && !err && !(var95 == null && var99 == null) && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          <li>
            95%:{' '}
            <button
              onClick={() =>
                var95 != null &&
                getVarBreakdown(owner, { days, confidence: 95 })
                  .then((d) => setBreakdown(d))
                  .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
              }
              disabled={var95 == null}
            >
              {format(var95)}
            </button>
          </li>
          <li>
            99%:{' '}
            <button
              onClick={() =>
                var99 != null &&
                getVarBreakdown(owner, { days, confidence: 99 })
                  .then((d) => setBreakdown(d))
                  .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
              }
              disabled={var99 == null}
            >
              {format(var99)}
            </button>
          </li>
        </ul>
      )}
      {breakdown && (
        <VarBreakdownModal
          contributions={breakdown}
          onClose={() => setBreakdown(null)}
        />
      )}
    </div>
  );
}

export default ValueAtRisk;

