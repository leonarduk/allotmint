import { useEffect, useState } from "react";
import { getQuotes } from "../api";
import type { Quote } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import "../styles/watchlist.css";

const DEFAULT_SYMBOLS =
  "^FTSE,^NDX,^GSPC,^RUT,^NYA,^VIX,^GDAXI,^N225,GBPUSD=X,GBPEUR=X,BTC-USD,GC=F,SI=F,VUSA.L,IWDA.AS";

type SortKey = keyof Quote;

function formatPrice(q: Quote): string {
  if (q.last == null) return "—";
  let dp = 2;
  const sym = q.symbol;
  if (sym.includes("=X")) dp = 5;
  else if (q.last > 10000) dp = 0;
  else if (q.last < 1 && (sym.includes("-USD") || sym.endsWith("=F"))) dp = 5;
  return new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  }).format(q.last);
}

function formatChange(val: number | null, dp = 2): string {
  return val == null ? "—" : val.toFixed(dp);
}

function formatVolume(v: number | null): string {
  return v == null ? "—" : new Intl.NumberFormat("en-GB").format(v);
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", { timeZone: "Europe/London" });
}

export function Watchlist() {
  const [symbols, setSymbols] = useState(
    localStorage.getItem("watchlistSymbols") || DEFAULT_SYMBOLS,
  );
  const [rows, setRows] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);

  const { sorted, handleSort } = useSortableTable<Quote, SortKey>(rows, "symbol");

  async function load() {
    try {
      const data = await getQuotes(symbols);
      setRows(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
    if (!auto) return;
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [symbols, auto]);

  function handleSymbolsChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setSymbols(v);
    localStorage.setItem("watchlistSymbols", v);
  }

  return (
    <div style={{ padding: "1rem" }}>
      <h1>Watchlist</h1>
      <div style={{ marginBottom: "1rem", display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <input
          value={symbols}
          onChange={handleSymbolsChange}
          style={{ minWidth: "400px" }}
          placeholder="Comma separated symbols"
        />
        <label>
          <input
            type="checkbox"
            checked={auto}
            onChange={(e) => setAuto(e.target.checked)}
          />
          Auto refresh
        </label>
      </div>
      {error && <div className="toast">Error: {error}</div>}
      <table className="watchlist-table">
        <thead>
          <tr>
            {[
              "name",
              "symbol",
              "last",
              "open",
              "high",
              "low",
              "change",
              "changePct",
              "volume",
              "time",
            ].map((k) => (
              <th key={k} onClick={() => handleSort(k as SortKey)}>
                {k === "changePct" ? "Chg %" : k.charAt(0).toUpperCase() + k.slice(1)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((q) => {
            const colour = q.change == null || q.change === 0 ? "" : q.change > 0 ? "pos" : "neg";
            return (
              <tr key={q.symbol}>
                <td title={q.name}>{q.name}</td>
                <td>{q.symbol}</td>
                <td className="num">{formatPrice(q)}</td>
                <td className="num">{formatChange(q.open)}</td>
                <td className="num">{formatChange(q.high)}</td>
                <td className="num">{formatChange(q.low)}</td>
                <td className={`num ${colour}`}>{formatChange(q.change)}</td>
                <td className={`num ${colour}`}>{formatChange(q.changePct)}</td>
                <td className="num">{formatVolume(q.volume)}</td>
                <td className="num">{formatTime(q.time)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default Watchlist;
