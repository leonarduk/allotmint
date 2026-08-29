import { useEffect, useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { getQuotes } from "../api";
import type { QuoteRow } from "../types";

const DEFAULT_SYMBOLS =
  "^FTSE,^NDX,^GSPC,^RUT,^NYA,^VIX,^GDAXI,^N225,USDGBP=X,EURGBP=X,BTC-USD,GC=F,SI=F,VUSA.L,IWDA.AS";

// Decimal precision for a price-like value, keyed off the symbol (and, for
// crypto, the magnitude of the value itself). This used to be duplicated
// between formatValue and formatChange with two different rule sets --
// formatChange was hardcoded to toFixed(2), so an EURGBP=X move that
// formatValue correctly rendered to 5 decimal places (0.85721) showed up as
// "+0.00" in the Chg column even though Chg % reported it correctly. Both
// formatters now call this single function so the rules can't drift apart
// again (#7218).
function pricePrecision(symbol: string, val: number): number {
  if (symbol.endsWith("=X")) return 5;
  if (symbol === "^TNX") return 3;
  if (symbol.includes("-USD") && val < 1) return 5;
  if (val > 10000) return 0;
  return 2;
}

function formatValue(symbol: string, val: number | null): string {
  if (val == null) return "—";
  return val.toFixed(pricePrecision(symbol, val));
}

function formatChange(symbol: string, val: number | null): string {
  if (val == null) return "—";
  const num = val.toFixed(pricePrecision(symbol, val));
  return val > 0 ? `+${num}` : num;
}

function formatPct(val: number | null): string {
  if (val == null) return "—";
  const num = val.toFixed(2);
  return (val > 0 ? "+" : "") + num + "%";
}

// ^-prefixed indices (^FTSE, ^VIX, ...) and =X FX rate pairs don't have a
// meaningful traded volume, but the feed reports literal 0 for them rather
// than null. Rendered as "0" that reads as "nothing traded today", which is
// false -- treat it as unavailable instead. A genuine 0 volume on an equity
// or ETF row is left alone: we have no way to distinguish "no trades yet
// today" from "not applicable" there, so we only special-case the symbol
// shapes that structurally never report volume (#7218).
function isVolumelessSymbolType(symbol: string): boolean {
  return symbol.startsWith("^") || symbol.endsWith("=X");
}

function formatVol(symbol: string, val: number | null): string {
  if (val == null) return "—";
  if (val === 0 && isVolumelessSymbolType(symbol)) return "—";
  return val.toLocaleString("en-GB");
}

function formatTime(val: string | null): string {
  if (!val) return "—";
  return new Date(val).toLocaleString("en-GB", { timeZone: "Europe/London" });
}

// The quote payload (backend/routes/quotes.py -> getQuotes in api.ts) does
// not currently carry a currency/unit field, so derive it from the symbol
// shape the same way pricePrecision() does for its special cases (#7218).
// This is deliberately a small, explicit table rather than an exhaustive
// exchange-suffix list -- it covers the default watchlist symbols plus the
// common exchange suffixes a user is likely to add, and falls back to USD
// (the yfinance default) for anything else.
function symbolUnit(symbol: string): string {
  if (symbol.endsWith("=X")) {
    // FX rate, e.g. EURGBP=X -> "EUR/GBP": a ratio, not a currency amount.
    const pair = symbol.slice(0, -2);
    return pair.length === 6 ? `${pair.slice(0, 3)}/${pair.slice(3)}` : "rate";
  }
  if (symbol === "^TNX") return "%"; // CBOE 10-Year Treasury yield index
  if (symbol.startsWith("^")) return "pts"; // index points
  if (symbol.includes("-USD")) return "USD"; // crypto pairs, e.g. BTC-USD
  if (symbol.endsWith("=F")) return "USD"; // commodity futures, e.g. GC=F
  if (symbol.endsWith(".L")) return "GBp"; // LSE listings are quoted in pence
  if (
    symbol.endsWith(".AS") ||
    symbol.endsWith(".PA") ||
    symbol.endsWith(".DE") ||
    symbol.endsWith(".MI")
  )
    return "EUR";
  if (symbol.endsWith(".SW")) return "CHF";
  if (symbol.endsWith(".TO")) return "CAD";
  if (symbol.endsWith(".HK")) return "HKD";
  return "USD";
}

// InstrumentResearch (the /instrument/:ticker page) only accepts tickers
// matching this shape -- indices (^FTSE) and FX pairs (EURGBP=X) fail it and
// have no instrument page. Reuse the same rule here so a watchlist row only
// links through when the symbol actually resolves to a known instrument
// (#7218).
function isLinkableSymbol(symbol: string): boolean {
  return /^[A-Za-z0-9.-]{1,10}$/.test(symbol);
}

export function Watchlist() {
  const { t } = useTranslation();
  const [symbols, setSymbols] = useState(() =>
    localStorage.getItem("watchlistSymbols") || DEFAULT_SYMBOLS,
  );
  const [newSymbol, setNewSymbol] = useState("");
  const [intervalMs, setIntervalMs] = useState(60000);
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [auto, setAuto] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allClosed, setAllClosed] = useState(false);
  const [sortKey, setSortKey] = useState<keyof QuoteRow>("symbol");
  const [asc, setAsc] = useState(true);

  const symbolList = useMemo(
    () => symbols.split(",").map((s) => s.trim()).filter(Boolean),
    [symbols],
  );

  const addSymbol = useCallback(() => {
    // Accept a comma-separated paste as well as a single ticker: the field
    // this replaced held the whole CSV list, so pasting one back in is the
    // obvious move for anyone restoring a watchlist -- and splitting here
    // stops "AAA,BBB" being stored as one unquotable symbol (#7110).
    const candidates = newSymbol
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (!candidates.length) {
      setNewSymbol("");
      return;
    }
    const seen = new Set(symbolList.map((s) => s.toUpperCase()));
    const additions = candidates.filter((c) => !seen.has(c) && seen.add(c));
    if (additions.length) {
      setSymbols([...symbolList, ...additions].join(","));
    }
    setNewSymbol("");
  }, [newSymbol, symbolList]);

  const removeSymbol = useCallback(
    (symbol: string) => {
      setSymbols(symbolList.filter((s) => s !== symbol).join(","));
    },
    [symbolList],
  );

  const fetchData = useCallback(async () => {
    if (!symbolList.length) {
      setRows([]);
      return;
    }
    try {
      const data = (await getQuotes(symbolList)) as QuoteRow[];
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
        <label htmlFor="watchlist-symbol-input" className="mb-1 block">
          {t("watchlist.symbolsLabel", { defaultValue: "Watched tickers" })}
        </label>
        <div className="mb-1 flex flex-wrap gap-1">
          {symbolList.map((s) => (
            <span
              key={s}
              className="flex items-center gap-1 rounded border px-2 py-0.5"
            >
              {s}
              <button
                type="button"
                aria-label={t("watchlist.removeSymbol", {
                  defaultValue: "Remove {{symbol}}",
                  symbol: s,
                })}
                onClick={() => removeSymbol(s)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-1">
          <input
            id="watchlist-symbol-input"
            className="w-full"
            value={newSymbol}
            placeholder={t("watchlist.symbolsPlaceholder", {
              defaultValue:
                "Add a ticker (e.g. ^FTSE, EURGBP=X, VUSA.L) and press Enter",
            })}
            aria-label={t("watchlist.symbolsLabel", {
              defaultValue: "Watched tickers",
            })}
            onChange={(e) => setNewSymbol(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSymbol();
              }
            }}
          />
          <button type="button" onClick={addSymbol}>
            {t("watchlist.addSymbol", { defaultValue: "Add" })}
          </button>
        </div>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
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
        <div className="mb-2 text-gray-800 dark:text-gray-200">
          {t("watchlist.marketsClosed", { defaultValue: "Markets closed" })}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {([
                { k: "name", l: t("watchlist.columnName", { defaultValue: "Name" }) },
                { k: "symbol", l: t("watchlist.columnSymbol", { defaultValue: "Symbol" }) },
                // Not a sortable QuoteRow field -- it's derived per-row from
                // the symbol (#7218) -- so it isn't given a sort key below.
                { k: "unit", l: t("watchlist.columnUnit", { defaultValue: "Unit" }), unsortable: true },
                { k: "last", l: t("watchlist.columnLast", { defaultValue: "Last" }) },
                { k: "open", l: t("watchlist.columnOpen", { defaultValue: "Open" }) },
                { k: "high", l: t("watchlist.columnHigh", { defaultValue: "High" }) },
                { k: "low", l: t("watchlist.columnLow", { defaultValue: "Low" }) },
                { k: "change", l: t("watchlist.columnChange", { defaultValue: "Chg" }) },
                { k: "changePct", l: t("watchlist.columnChangePct", { defaultValue: "Chg %" }) },
                { k: "volume", l: t("watchlist.columnVolume", { defaultValue: "Vol" }) },
                {
                  k: "marketTime",
                  l: t("watchlist.columnTime", { defaultValue: "Time (Europe/London)" }),
                  minWidth: 88,
                },
              ] satisfies {
                k: keyof QuoteRow | "unit";
                l: string;
                minWidth?: number;
                unsortable?: boolean;
              }[]).map((c) => (
                <th
                  key={c.k}
                  onClick={
                    c.unsortable ? undefined : () => toggleSort(c.k as keyof QuoteRow)
                  }
                  style={{
                    cursor: c.unsortable ? "default" : "pointer",
                    textAlign: c.k === "name" || c.k === "symbol" ? "left" : "right",
                    borderBottom: "1px solid #ccc",
                    padding: "4px 6px",
                    whiteSpace: "nowrap",
                    minWidth: "minWidth" in c ? c.minWidth : undefined,
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
              const linkable = isLinkableSymbol(r.symbol);
              // The instrument-page link and the row's own hover title both
              // want the full instrument name; keeping the anchor's text
              // untruncated (with only the surrounding <td> clipped by CSS)
              // means the browser's own tooltip and screen readers still see
              // the whole thing even where our title attribute doesn't apply
              // (#7218).
              const nameCell = (
                <span title={r.name || undefined}>{r.name || "—"}</span>
              );
              return (
                <tr key={r.symbol}>
                  <td
                    style={{
                      // Widened from 160 -- with the full name now shown via
                      // title (#7218), a bit more room means fewer of the
                      // very common ETF names need the ellipsis at all. The
                      // remaining truncation for very long names such as
                      // "iShares Core MSCI World UCITS ETF..." is a CSS
                      // ellipsis, not a data truncation: the yfinance
                      // shortName/longName fields returned by
                      // backend/routes/quotes.py already carry the full
                      // name, it's just this column's width that clips it.
                      maxWidth: 220,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      padding: "4px 6px",
                    }}
                  >
                    {linkable ? (
                      <Link to={`/instrument/${r.symbol}`} title={r.name || undefined}>
                        {r.name || "—"}
                      </Link>
                    ) : (
                      nameCell
                    )}
                  </td>
                  <td style={{ padding: "4px 6px" }}>
                    {linkable ? (
                      <Link to={`/instrument/${r.symbol}`}>{r.symbol}</Link>
                    ) : (
                      r.symbol
                    )}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {symbolUnit(r.symbol)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatValue(r.symbol, r.last)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatValue(r.symbol, r.open)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatValue(r.symbol, r.high)}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {formatValue(r.symbol, r.low)}
                  </td>
                  <td
                    style={{
                      textAlign: "right",
                      color,
                      padding: "4px 6px",
                    }}
                  >
                    {formatChange(r.symbol, r.change)}
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
                    {formatVol(r.symbol, r.volume)}
                  </td>
                  <td style={{ minWidth: 88, padding: "4px 6px" }}>{formatTime(r.marketTime)}</td>
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
