import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { getQuotes } from "../api";
import type { QuoteRow } from "../types";
import { priceDecimals } from "../utils/priceFormatting";
import { setWatchlistSymbols, useWatchlists } from "../lib/watchlistStore";
import WatchlistBar from "../components/WatchlistBar";
import { useWatchlistUrlParam } from "../hooks/useWatchlistUrlParam";
import TableRowsSkeleton from "../components/skeletons/TableRowsSkeleton";

const WATCHLIST_COLUMN_COUNT = 11;


function formatValue(symbol: string, val: number | null): string {
  if (val == null) return "—";
  return val.toFixed(priceDecimals(symbol, val));
}

function formatChange(
  symbol: string,
  val: number | null,
  refPrice: number | null,
): string {
  if (val == null) return "—";
  const num = val.toFixed(priceDecimals(symbol, val, refPrice ?? val));
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

const DAY_MS = 24 * 60 * 60 * 1000;

// Whole days a row's quote trails the newest quote in the table. Rows from
// different exchanges legitimately differ by hours, so only a gap of a full
// day or more counts -- that's a closed/stale market sitting next to live
// prices, e.g. a Friday index level beside Sunday FX quotes (#7819).
function staleDays(val: string | null, newestMs: number | null): number | null {
  if (!val || newestMs == null) return null;
  const days = Math.floor((newestMs - new Date(val).getTime()) / DAY_MS);
  return days >= 1 ? days : null;
}

// CBOE Treasury-yield indices: their "price" is a yield in percent, not a
// currency amount or a raw index-points level.
const YIELD_INDEX_SYMBOLS = new Set(["^TNX", "^TYX", "^FVX", "^IRX"]);

// Fallback used only when the quote payload doesn't carry a currency
// (see symbolUnit below). Deliberately a small, explicit table rather than
// an exhaustive exchange-suffix list, and deliberately *not* a confident
// guess for anything it doesn't recognise: mislabelling a real currency is
// worse than admitting we don't know, since the whole point of this column
// is telling a beginner what's real (#7218). In particular this table does
// NOT assume every ".L"/".DE"/".SW" listing uses that market's home
// currency -- LSE, Xetra and SIX all list plenty of USD- and
// EUR-denominated lines too, which is exactly why the live `currency` field
// (added to backend/routes/quotes.py) is preferred whenever it's present.
function symbolUnitFallback(symbol: string): string {
  if (symbol.endsWith("=X")) {
    // FX rate, e.g. EURGBP=X -> "EUR/GBP": a ratio, not a currency amount.
    const pair = symbol.slice(0, -2);
    return pair.length === 6 ? `${pair.slice(0, 3)}/${pair.slice(3)}` : "rate";
  }
  if (YIELD_INDEX_SYMBOLS.has(symbol)) return "%";
  if (symbol.startsWith("^")) return "pts"; // index points
  if (symbol.includes("-USD")) return "USD"; // crypto pairs, e.g. BTC-USD
  if (symbol.endsWith("=F")) return "USD"; // commodity futures, e.g. GC=F
  // Below this point we're guessing at an exchange's *typical* currency,
  // not reading it off the symbol the way the cases above do -- kept only
  // as a best-effort label for the common default-watchlist exchanges.
  if (symbol.endsWith(".L")) return "GBp"; // most LSE main-market listings
  if (
    symbol.endsWith(".AS") ||
    symbol.endsWith(".PA") ||
    symbol.endsWith(".MI")
  )
    return "EUR";
  return "—"; // unknown -- do not guess (#7218)
}

// Prefer the currency the quote payload actually reports; only fall back to
// guessing from the symbol shape when the feed didn't send one (#7218).
// `quoteType` (from the provider, see backend/routes/quotes.py) takes
// priority over a reported currency for indices: an index level is a points
// figure, not a currency amount, even when the feed also sends a currency
// code alongside it (#7232).
function symbolUnit(
  symbol: string,
  currency: string | null | undefined,
  quoteType?: string | null,
): string {
  if (quoteType === "INDEX") return "pts";
  if (currency) return currency;
  return symbolUnitFallback(symbol);
}

// Row links go to /research/:ticker (InstrumentResearch), NOT
// /instrument/:group -- that second route is the instrument *catalogue
// editor* filtered by group slug (routes/registry.ts, InstrumentTable.tsx)
// and would treat a ticker like "VUSA.L" as an unknown group, firing a
// pointless getGroupInstruments("VUSA.L") call and showing an empty/error
// catalogue instead of the research page. Confirmed via routes/registry.ts
// (mode: 'research', routeSegment: 'research') and App.tsx's route for
// InstrumentResearch (#7218).
const INSTRUMENT_ROUTE_PREFIX = "/research/";

// InstrumentResearch only accepts tickers matching this shape (the same
// regex guards `tkr` in pages/InstrumentResearch.tsx) -- indices (^FTSE), FX
// pairs (EURGBP=X) and commodity futures (GC=F) fail it and have no research
// page, while crypto pairs such as BTC-USD pass. Reuse the same rule here so
// a watchlist row only links through when the research page will accept the
// symbol (#7218, #7330).
function isLinkableSymbol(symbol: string): boolean {
  return /^[A-Za-z0-9.-]{1,10}$/.test(symbol);
}

// Ticker shapes the quote feed accepts: equities/ETFs (VUSA.L, BRK-B),
// indices (^FTSE), FX pairs (EURGBP=X), futures (GC=F) and crypto
// (BTC-USD). Anything else -- notably a space inside a symbol -- is stored
// verbatim and can never be quoted, so it is rejected up front (#7174).
const SYMBOL_PATTERN = /^[A-Z0-9.^=-]{1,20}$/;

interface SymbolInputResult {
  additions: string[];
  invalid: string[];
  duplicates: string[];
}

// Splits the add field into new, invalid and already-watched tickers. A
// comma-separated paste is accepted as well as a single ticker: the field
// this replaced held the whole CSV list, so pasting one back in is the
// obvious move for anyone restoring a watchlist (#7110).
function classifySymbolInput(
  raw: string,
  existing: readonly string[],
): SymbolInputResult {
  const already = new Set(existing.map((s) => s.toUpperCase()));
  const seen = new Set<string>();
  const result: SymbolInputResult = {
    additions: [],
    invalid: [],
    duplicates: [],
  };
  for (const part of raw.split(",")) {
    const symbol = part.trim().toUpperCase();
    if (!symbol) continue;
    if (!SYMBOL_PATTERN.test(symbol)) result.invalid.push(symbol);
    else if (already.has(symbol)) result.duplicates.push(symbol);
    // A symbol repeated within one paste is just deduped: it was never
    // "already in this watchlist", so it must not be reported as such.
    else if (!seen.has(symbol)) {
      seen.add(symbol);
      result.additions.push(symbol);
    }
  }
  return result;
}

export function Watchlist() {
  const { t } = useTranslation();
  const { active } = useWatchlists();
  const missingList = useWatchlistUrlParam();
  const activeId = active.id;
  const symbolList = active.symbols;
  const [newSymbol, setNewSymbol] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [intervalMs, setIntervalMs] = useState(60000);
  const [rows, setRows] = useState<QuoteRow[]>([]);
  const [auto, setAuto] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allClosed, setAllClosed] = useState(false);
  // False until the first quote request settles, so the table shows a
  // loading skeleton rather than bare headers that read as "empty watchlist"
  // (#7788 item 5). Later refreshes keep showing the previous rows.
  const [hasLoaded, setHasLoaded] = useState(false);
  const [sortKey, setSortKey] = useState<keyof QuoteRow>("symbol");
  const [asc, setAsc] = useState(true);

  const addSymbol = useCallback(() => {
    const { additions, invalid, duplicates } = classifySymbolInput(
      newSymbol,
      symbolList,
    );
    if (additions.length) {
      setWatchlistSymbols(activeId, [...symbolList, ...additions]);
    }
    // Keep rejected text in the field so it can be corrected; never clear
    // silently, which used to read as "added" (#7147, #7174).
    setNewSymbol(invalid.join(", "));
    if (invalid.length) {
      setInputError(
        t("watchlist.symbolInvalid", { symbols: invalid.join(", ") }),
      );
    } else if (duplicates.length) {
      setInputError(
        t("watchlist.symbolDuplicate", { symbols: duplicates.join(", ") }),
      );
    } else if (!additions.length) {
      setInputError(t("watchlist.symbolEmpty"));
    } else {
      setInputError(null);
    }
  }, [newSymbol, symbolList, activeId, t]);

  const removeSymbol = useCallback(
    (symbol: string) => {
      setWatchlistSymbols(
        activeId,
        symbolList.filter((s) => s !== symbol),
      );
    },
    [symbolList, activeId],
  );

  // Switching lists: drop the previous list's rows and show the loading
  // skeleton rather than briefly mixing two lists' quotes.
  useEffect(() => {
    setRows([]);
    setHasLoaded(false);
    setAllClosed(false);
  }, [activeId]);

  // Only the latest request may update the table, so a slow response for
  // a list the user has since switched away from can't overwrite it.
  const requestSeq = useRef(0);

  const fetchData = useCallback(async () => {
    const seq = ++requestSeq.current;
    if (!symbolList.length) {
      setRows([]);
      return;
    }
    try {
      const data = (await getQuotes(symbolList)) as QuoteRow[];
      if (seq !== requestSeq.current) return;
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
      if (seq !== requestSeq.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (seq === requestSeq.current) setHasLoaded(true);
    }
  }, [symbolList]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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

  const newestMs = useMemo(() => {
    const times = rows
      .map((r) => (r.marketTime ? new Date(r.marketTime).getTime() : NaN))
      .filter((ms) => !Number.isNaN(ms));
    return times.length ? Math.max(...times) : null;
  }, [rows]);

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
      <WatchlistBar />
      {missingList && (
        <div role="status" className="mb-2 text-amber-700 dark:text-amber-300">
          {t("watchlist.listNotFound", {
            name: missingList,
            shown: active.name,
          })}
        </div>
      )}
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
            aria-invalid={inputError ? true : undefined}
            aria-describedby={inputError ? "watchlist-symbol-error" : undefined}
            onChange={(e) => {
              setNewSymbol(e.target.value);
              setInputError(null);
            }}
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
        {inputError && (
          <p
            id="watchlist-symbol-error"
            role="alert"
            className="mt-1 text-sm text-red-600 dark:text-red-400"
          >
            {inputError}
          </p>
        )}
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
        <div className="mb-2 break-words text-red-500 [overflow-wrap:anywhere]">
          {error}
        </div>
      )}
      {allClosed && (
        <div className="mb-2 text-[var(--surface-card-color)]">
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
            {!hasLoaded && symbolList.length > 0 && (
              <TableRowsSkeleton
                rows={Math.min(symbolList.length, 8)}
                colSpan={WATCHLIST_COLUMN_COUNT}
                label={t("watchlist.loading", { defaultValue: "Loading quotes…" })}
              />
            )}
            {sorted.map((r) => {
              const color = r.change ? (r.change > 0 ? "green" : "red") : undefined;
              const pctBg =
                r.changePct != null && r.changePct !== 0
                  ? r.changePct > 0
                    ? `rgba(0,128,0,${Math.min(Math.abs(r.changePct) / 5, 0.5)})`
                    : `rgba(255,0,0,${Math.min(Math.abs(r.changePct) / 5, 0.5)})`
                  : undefined;
              const linkable = isLinkableSymbol(r.symbol);
              const ageDays = staleDays(r.marketTime, newestMs);
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
                      // The backend now prefers yfinance's longName over its
                      // hard-truncated (31-char) shortName (#7218/#7232), so
                      // the name reaching here is already the real, full
                      // instrument name -- an ellipsis/nowrap clip would just
                      // re-introduce the truncation at the CSS layer instead
                      // of the data layer. Wrap it instead so the full name
                      // stays visible.
                      maxWidth: 220,
                      whiteSpace: "normal",
                      wordBreak: "break-word",
                      padding: "4px 6px",
                    }}
                  >
                    {linkable ? (
                      <Link
                        to={`${INSTRUMENT_ROUTE_PREFIX}${r.symbol}`}
                        title={r.name || undefined}
                      >
                        {r.name || "—"}
                      </Link>
                    ) : (
                      nameCell
                    )}
                  </td>
                  <td style={{ padding: "4px 6px" }}>
                    {linkable ? (
                      <Link to={`${INSTRUMENT_ROUTE_PREFIX}${r.symbol}`}>
                        {r.symbol}
                      </Link>
                    ) : (
                      r.symbol
                    )}
                  </td>
                  <td style={{ textAlign: "right", padding: "4px 6px" }}>
                    {symbolUnit(r.symbol, r.currency, r.quoteType)}
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
                    {formatChange(r.symbol, r.change, r.last)}
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
                  <td style={{ minWidth: 88, padding: "4px 6px" }}>
                    {formatTime(r.marketTime)}
                    {ageDays != null && (
                      <span className="ml-1 rounded bg-amber-100 px-1 text-xs text-amber-900 dark:bg-amber-900 dark:text-amber-100">
                        {t("watchlist.staleAge", {
                          defaultValue: "{{days}}d old",
                          days: ageDays,
                        })}
                      </span>
                    )}
                  </td>
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
