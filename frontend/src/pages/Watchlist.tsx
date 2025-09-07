import { useEffect, useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { getQuotes } from "../api";
import type { QuoteRow } from "../types";

interface QuoteWithState extends QuoteRow {
  marketState?: string;
}

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
  const [intervalMs, setIntervalMs] = useState(60000);
  const [rows, setRows] = useState<QuoteWithState[]>([]);
  const [auto, setAuto] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allClosed, setAllClosed] = useState(false);
  const [sortKey, setSortKey] = useState<keyof QuoteRow>("symbol");
  const [asc, setAsc] = useState(true);

  const symbolList = useMemo(
    () => symbols.split(",").map((s) => s.trim()).filter(Boolean),
    [symbols],
  );

  const fetchData = useCallback(async () => {
    if (!symbolList.length) {
      setRows([]);
      return;
    }
    try {
      const data = (await getQuotes(symbolList)) as QuoteWithState[];
      setRows(data);
      setError(null);

      const closed =
        data.length > 0 &&
        data.every((r) => r.marketState && r.marketState !== "REGULAR");

      setAllClosed((prev) => {
        if (closed) {
          if (!prev) {
            setAuto(false);
          }
          return true;
        }
        if (prev) {
          setAuto(true);
        }
        return false;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [symbolList]);

  useEffect(() => {
    fetchData();
    localStorage.setItem("watchlistSymbols", symbols);
  }, [fetchData, symbols]);

  useEffect(() => {
    if (intervalMs <= 0 || auto) return;
    const id = setInterval(fetchData, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, auto, fetchData]);

  useEffect(() => {
    if (intervalMs <= 0) return;
    if (auto) {
      const id = setInterval(fetchData, 10000);
      return () => clearInterval(id);
    }
    if (!allClosed) {
      const id = setInterval(fetchData, 60000);
      return () => clearInterval(id);
    }
  }, [auto, allClosed, fetchData, intervalMs]);

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
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">
        {t("watchlist.title", { defaultValue: "Watchlist" })}
      </h1>
      <div className="mb-2">
        <input
          className="w-full"
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
        />
      </div>
      <div className="mb-2 flex items-center gap-2">
        <label className="flex items-center gap-1">
          {t("watchlist.refreshFrequency", { defaultValue: "Auto-refresh" })}
          <select
            value={intervalMs}
            onChange={(e) => setIntervalMs(Number(e.target.value))}
          >
            <option value={60000}>
              {t("watchlist.everyMinute", { defaultValue: "Every minute" })}
            </option>
            <option value={0}>
              {t("watchlist.manual", { defaultValue: "Manual" })}
            </option>
          </select>
        </label>
        <button onClick={fetchData}>{t("watchlist.refresh")}</button>
      </div>
      {error && (
        <div className="mb-2 text-red-500">{error}</div>
      )}
      {allClosed && (
        <div className="mb-2 text-gray-500">
          {t("watchlist.marketsClosed", { defaultValue: "Markets closed" })}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
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
                { k: "marketTime", l: "Time" },
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
                  <td style={{ padding: "4px 6px" }}>{formatTime(r.marketTime)}</td>
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
