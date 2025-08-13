import { useEffect, useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getQuotes } from "../api";
import type { QuoteRow } from "../types";

const DEFAULT_SYMBOLS =
  "^FTSE,^NDX,^GSPC,^RUT,^NYA,^VIX,^GDAXI,^N225,USDGBP=X,EURGBP=X,BTC-USD,GC=F,SI=F,VUSA.L,IWDA.AS";

function formatPrice(symbol: string, val: number | null): string {
  if (val == null) return "—";
  if (symbol.endsWith("=X")) return val.toFixed(5);
  if (symbol === "^TNX") return val.toFixed(3);
  if (symbol.includes("-USD") && val < 1) return val.toFixed(5);
  if (val > 10000) return val.toFixed(0);
  return val.toFixed(2);
}

function formatChange(val: number | null): string {
  if (val == null) return "—";
  const num = val.toFixed(2);
  return val > 0 ? `+${num}` : num;
}

function formatPct(val: number | null): string {
  if (val == null) return "—";
  const num = val.toFixed(2);
  return (val > 0 ? "+" : "") + num + "%";
}

function formatVol(val: number | null): string {
  if (val == null) return "—";
  return val.toLocaleString("en-GB");
}

function formatTime(val: string | null): string {
  if (!val) return "—";
  return new Date(val).toLocaleString("en-GB", { timeZone: "Europe/London" });
}

export function Watchlist() {
  const { t } = useTranslation();
  const [symbols, setSymbols] = useState(() =>
    localStorage.getItem("watchlistSymbols") || DEFAULT_SYMBOLS,
  );
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [auto, setAuto] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<keyof QuoteRow>("symbol");
  const [asc, setAsc] = useState(true);

  const symbolList = useMemo(
    () => symbols.split(",").map((s) => s.trim()).filter(Boolean),
    [symbols],
  );

  async function fetchData() {
    if (!symbolList.length) {
      setRows([]);
      return;
    }
    try {
      const data = await getQuotes(symbolList);
      setRows(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    fetchData();
    localStorage.setItem("watchlistSymbols", symbols);
  }, [symbols]);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(fetchData, 10000);
    return () => clearInterval(id);
  }, [auto, symbols]);

  const sorted = useMemo(() => {
    const data = [...rows];
    data.sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string" && typeof vb === "string") {
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return asc ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
    return data;
  }, [rows, sortKey, asc]);

  function toggleSort(k: keyof QuoteRow) {
    if (sortKey === k) {
      setAsc(!asc);
    } else {
      setSortKey(k);
      setAsc(true);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: "0.5rem" }}>
        <input
          style={{ width: "100%" }}
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
        />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          marginBottom: "0.5rem",
        }}
      >
        <label style={{ display: "flex", alignItems: "center" }}>
          <input
            type="checkbox"
            checked={auto}
            onChange={(e) => setAuto(e.target.checked)}
          />{" "}Auto-refresh
        </label>
        <button onClick={fetchData}>{t("watchlist.refresh")}</button>
      </div>
      {error && (
        <div style={{ color: "red", marginBottom: "0.5rem" }}>{error}</div>
      )}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {[
                { k: "name", l: "Name" },
                { k: "symbol", l: "Symbol" },
                { k: "last", l: "Last" },
                { k: "open", l: "Open" },
                { k: "high", l: "High" },
                { k: "low", l: "Low" },
                { k: "change", l: "Chg" },
                { k: "changePct", l: "Chg %" },
                { k: "volume", l: "Vol" },
                { k: "time", l: "Time" },
              ].map((c) => (
                <th
                  key={c.k}
                  onClick={() => toggleSort(c.k as keyof QuoteRow)}
                  style={{
                    cursor: "pointer",
                    textAlign: c.k === "name" || c.k === "symbol" ? "left" : "right",
                    borderBottom: "1px solid #ccc",
                    padding: "4px 6px",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const color = r.change ? (r.change > 0 ? "green" : "red") : undefined;
              const pctBg =
                r.changePct != null && r.changePct !== 0
                  ? r.changePct > 0
                    ? `rgba(0,128,0,${Math.min(Math.abs(r.changePct) / 5, 0.5)})`
                    : `rgba(255,0,0,${Math.min(Math.abs(r.changePct) / 5, 0.5)})`
                  : undefined;
              return (
                <tr key={r.symbol}>
                  <td
                    title={r.name || undefined}
                    style={{
                      maxWidth: 160,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      padding: "4px 6px",
                    }}
                  >
                    {r.name || "—"}
                  </td>
                  <td style={{ padding: "4px 6px" }}>{r.symbol}</td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatPrice(r.symbol, r.last)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatPrice(r.symbol, r.open)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatPrice(r.symbol, r.high)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatPrice(r.symbol, r.low)}
                  </td>
                  <td
                    style={{
                      textAlign: "right",
                      color,
                      padding: "4px 6px",
                    }}
                  >
                    {formatChange(r.change)}
                  </td>
                  <td
                    style={{
                      textAlign: "right",
                      color,
                      background: pctBg,
                      padding: "4px 6px",
                    }}
                  >
                    {formatPct(r.changePct)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatVol(r.volume)}
                  </td>
                  <td style={{ padding: "4px 6px" }}>{formatTime(r.time)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Watchlist;
