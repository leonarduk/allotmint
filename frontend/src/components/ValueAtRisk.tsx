import {useEffect, useState} from "react";
import {getValueAtRisk} from "../api";

interface Props {
  owner: string;
}

export function ValueAtRisk({owner}: Props) {
  const [days, setDays] = useState<number>(30);
  const [var95, setVar95] = useState<number | null>(null);
  const [var99, setVar99] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!owner) return;
    setLoading(true);
    setErr(null);
    Promise.all([
      getValueAtRisk(owner, {days, confidence: 95}),
      getValueAtRisk(owner, {days, confidence: 99}),
    ])
      .then(([d95, d99]) => {
        setVar95(d95.length ? d95[d95.length - 1].var : null);
        setVar99(d99.length ? d99[d99.length - 1].var : null);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [owner, days]);

  const format = (v: number | null) =>
    v != null
      ? `£${v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
      : "–";

  return (
    <div style={{marginBottom: "2rem"}}>
      <h2>Value at Risk</h2>
      <div style={{marginBottom: "0.5rem"}}>
        <label style={{fontSize: "0.85rem"}}>
          Period:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={{marginLeft: "0.25rem"}}
          >
            <option value={7}>1W</option>
            <option value={30}>1M</option>
            <option value={90}>3M</option>
            <option value={365}>1Y</option>
          </select>
        </label>
      </div>
      {loading && <div>Loading…</div>}
      {err && <div style={{color: "red"}}>{err}</div>}
      {!loading && !err && (
        <ul style={{listStyle: "none", padding: 0, margin: 0}}>
          <li>95%: {format(var95)}</li>
          <li>99%: {format(var99)}</li>
        </ul>
      )}
    </div>
  );
}

export default ValueAtRisk;
