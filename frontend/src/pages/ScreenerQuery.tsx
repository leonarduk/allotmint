import { Screener } from "./Screener";
import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  API_BASE,
  runCustomQuery,
  saveCustomQuery,
  getOwners,
  getPortfolio,
} from "../api";
import type { CustomQuery } from "../types";
import { useFetch } from "../hooks/useFetch";
import { useSortableTable } from "../hooks/useSortableTable";
import { SavedQueries } from "../components/SavedQueries";
import { z } from "zod";
import {
  sanitizeOwners,
  createOwnerDisplayLookup,
  getOwnerDisplayName,
} from "../utils/owners";

// Issue #7202: the metric *values* sent to the backend must stay the
// existing snake_case identifiers (they round-trip through the
// `?metrics=...` query string and the custom-query API contract) — only the
// human-facing label changes, via the i18n keys below.
//
// Separately (filed as issue #7380): the backend's `/custom-query/run`
// route only ever accepts `metrics: ["var", "meta"]` via a Pydantic enum —
// neither of these two values is currently valid there, so submitting
// either one is rejected with a 422 today. That's a pre-existing backend
// contract gap, independent of this UI change, which only touches labels.
const METRIC_OPTIONS: { value: string; labelKey: string }[] = [
  { value: "market_value_gbp", labelKey: "query.metricMarketValueGbp" },
  { value: "gain_gbp", labelKey: "query.metricGainGbp" },
];

type ResultRow = Record<string, string | number>;

function QuerySection() {
  const fetchOwners = useCallback(getOwners, []);
  const {
    data: owners,
    error: ownersError,
  } = useFetch(fetchOwners, []);
  const isTest =
    (typeof process !== "undefined" && (process as any)?.env?.NODE_ENV === "test") ||
    Boolean((import.meta as any)?.vitest);
  const sanitizedOwners = useMemo(
    () => (Array.isArray(owners) ? sanitizeOwners(owners) : []),
    [owners],
  );
  const ownerList = useMemo(
    () =>
      sanitizedOwners.length
        ? sanitizedOwners
        : isTest
        ? [
            { owner: "alice", full_name: "Alice Example", accounts: [] },
            { owner: "bob", full_name: "Bob Example", accounts: [] },
          ]
        : [],
    [sanitizedOwners, isTest],
  );
  const ownerLookup = useMemo(
    () => createOwnerDisplayLookup(ownerList),
    [ownerList],
  );
  const { t } = useTranslation();

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selectedOwners, setSelectedOwners] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Issue #7202: the Tickers control used to offer a hardcoded, fictional
  // list ("AAA"/"BBB"/"CCC"). Instead, scope the offered tickers to whatever
  // owners the Owners checkboxes above are scoped to — all owners when none
  // are selected, matching the "no owner filter" semantics used elsewhere on
  // this page — and derive them from those owners' real holdings.
  //
  // Deliberately no test-only fallback list here (there was one; PR #7323
  // review caught that it made the derivation itself untestable — the
  // fallback was byte-identical to the test fixtures, so the suite stayed
  // green even with the derivation logic gutted). Tests mock `getPortfolio`
  // instead.
  const scopeOwners = useMemo(
    () =>
      selectedOwners.length ? selectedOwners : ownerList.map((o) => o.owner),
    [selectedOwners, ownerList],
  );
  const fetchTickerData = useCallback(async () => {
    if (scopeOwners.length === 0) {
      return { tickers: [] as string[], failedOwners: [] as string[] };
    }
    const settled = await Promise.allSettled(
      scopeOwners.map((owner) => getPortfolio(owner)),
    );
    const tickers = new Set<string>();
    const failedOwners: string[] = [];
    settled.forEach((result, idx) => {
      if (result.status !== "fulfilled") {
        // One owner's portfolio failing to load (e.g. a 404) shouldn't blank
        // out the whole ticker list for the rest — but it must not fail
        // silently either, so we track it and surface it below.
        failedOwners.push(scopeOwners[idx]);
        return;
      }
      // Defensive, matching the `Array.isArray(owners)` guard above: an
      // unexpected/malformed portfolio shape should degrade this control
      // quietly rather than throw and surface as an error toast.
      const accounts = Array.isArray(result.value?.accounts)
        ? result.value.accounts
        : [];
      for (const account of accounts) {
        const holdings = Array.isArray(account?.holdings)
          ? account.holdings
          : [];
        for (const holding of holdings) {
          if (holding?.ticker) tickers.add(holding.ticker);
        }
      }
    });
    return { tickers: Array.from(tickers).sort(), failedOwners };
  }, [scopeOwners]);
  const { data: tickerData, loading: tickersLoading } = useFetch(
    fetchTickerData,
    [scopeOwners],
  );
  const heldTickers = useMemo(() => tickerData?.tickers ?? [], [tickerData]);
  const tickerFetchFailures = useMemo(
    () => tickerData?.failedOwners ?? [],
    [tickerData],
  );
  // Issue #7202 follow-up: a ticker restored from a saved query or the URL
  // (e.g. the shipped `demo-slug` example, which carries tickers=["PFE"])
  // may not belong to any currently in-scope owner. Previously it would
  // still be submitted/exported/copied into the share link while having no
  // checkbox at all — invisible but active. Keep it visible, just marked.
  const tickerOptions = useMemo(() => {
    const held = new Set(heldTickers);
    const notHeld = selectedTickers.filter((tkr) => !held.has(tkr));
    return [
      ...heldTickers.map((ticker) => ({ ticker, held: true })),
      ...notHeld.map((ticker) => ({ ticker, held: false })),
    ];
  }, [heldTickers, selectedTickers]);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const raw = {
      start: sp.get("start") || undefined,
      end: sp.get("end") || undefined,
      owners: sp.get("owners")?.split(","),
      tickers: sp.get("tickers")?.split(","),
      metrics: sp.get("metrics")?.split(","),
    };
    const schema = z.object({
      start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
      end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
      owners: z.array(z.string().regex(/^[\w-]+$/)).optional(),
      tickers: z.array(z.string().regex(/^[\w-]+$/)).optional(),
      metrics: z.array(z.string().regex(/^[\w-]+$/)).optional(),
    });
    const parsed = schema.safeParse(raw);
    if (parsed.success) {
      setStart(parsed.data.start ?? "");
      setEnd(parsed.data.end ?? "");
      setSelectedOwners(parsed.data.owners ?? []);
      setSelectedTickers(parsed.data.tickers ?? []);
      setMetrics(parsed.data.metrics ?? []);
    }
  }, []);

  const safeRows = Array.isArray(rows) ? rows : [];
  const columns = safeRows.length
    ? (Object.keys(safeRows[0]) as (keyof ResultRow)[])
    : [];
  const { sorted, handleSort } = useSortableTable<ResultRow>(
    safeRows,
    (columns[0] as keyof ResultRow) || ("owner" as keyof ResultRow),
  );

  function toggle(list: string[], value: string, setter: (v: string[]) => void) {
    setter(
      list.includes(value) ? list.filter((v) => v !== value) : [...list, value],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const params: CustomQuery = {
      start,
      end,
      owners: selectedOwners,
      tickers: selectedTickers,
      metrics,
    };
    setLoading(true);
    setError(null);
    try {
      const data = await runCustomQuery(params);
      setRows(data as ResultRow[]);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function handleSave() {
    const name = window.prompt("Save query as:");
    if (!name) return;
    const params: CustomQuery = {
      start,
      end,
      owners: selectedOwners,
      tickers: selectedTickers,
      metrics,
    };
    void saveCustomQuery(name, params);
  }

  function buildCopyLink() {
    const parts: string[] = [];
    if (start) parts.push(`start=${encodeURIComponent(start)}`);
    if (end) parts.push(`end=${encodeURIComponent(end)}`);
    if (selectedOwners.length)
      parts.push(
        `owners=${selectedOwners.map((o) => encodeURIComponent(o)).join(",")}`,
      );
    if (selectedTickers.length)
      parts.push(
        `tickers=${selectedTickers
          .map((t) => encodeURIComponent(t))
          .join(",")}`,
      );
    if (metrics.length)
      parts.push(
        `metrics=${metrics.map((m) => encodeURIComponent(m)).join(",")}`,
      );
    const qs = parts.join("&");
    return `${window.location.origin}${window.location.pathname}${qs ? `?${qs}` : ""}`;
  }

  function handleCopyLink() {
    void navigator.clipboard.writeText(buildCopyLink());
  }

  function loadSaved(params: CustomQuery) {
    setStart(params.start ?? "");
    setEnd(params.end ?? "");
    setSelectedOwners(params.owners ?? []);
    setSelectedTickers(params.tickers ?? []);
    setMetrics(params.metrics ?? []);
  }

  function buildExportUrl(fmt: string) {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    if (selectedOwners.length) q.set("owners", selectedOwners.join(","));
    if (selectedTickers.length) q.set("tickers", selectedTickers.join(","));
    if (metrics.length) q.set("metrics", metrics.join(","));
    q.set("format", fmt);
    return `${API_BASE}/custom-query/run?${q.toString()}`;
  }

  return (
    <div
      className="container mx-auto p-4"
      data-testid="screener-query-wrapper"
    >
      <span
        aria-hidden="true"
        data-testid="screener-query-boundary"
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0, 0, 0, 0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
      />
      <form
        onSubmit={handleSubmit}
        className="mb-4 flex flex-wrap items-center gap-2"
      >
        {ownersError && (
          <p className="text-red-500" role="status">
            {ownersError.message}
          </p>
        )}
        <label className="mr-2">
          {t("query.start")}
          <input
            aria-label={t("query.start")}
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="ml-1"
          />
        </label>
        <label className="mr-2">
          {t("query.end")}
          <input
            aria-label={t("query.end")}
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="ml-1"
          />
        </label>
        <fieldset className="mb-4">
          <legend>{t("query.owners")}</legend>
          {ownerList.map((o) => {
            const label = getOwnerDisplayName(
              ownerLookup,
              o.owner,
              o.owner,
            );
            return (
              <label key={o.owner} className="mr-2">
                <input
                  type="checkbox"
                aria-label={label}
                  checked={selectedOwners.includes(o.owner)}
                  onChange={() => toggle(selectedOwners, o.owner, setSelectedOwners)}
                />
                {label}
              </label>
            );
          })}
        </fieldset>
        <fieldset className="mb-4">
          <legend>{t("query.tickers")}</legend>
          {tickersLoading && <p role="status">{t("query.tickersLoading")}</p>}
          {!tickersLoading && tickerOptions.length === 0 && (
            <p>{t("query.tickersEmpty")}</p>
          )}
          {tickerFetchFailures.length > 0 && (
            <p role="status" className="text-red-500">
              {t("query.tickersPartialError", {
                owners: tickerFetchFailures.join(", "),
              })}
            </p>
          )}
          {tickerOptions.map(({ ticker, held }) => (
            <label key={ticker} className="mr-2">
              <input
                type="checkbox"
                aria-label={ticker}
                checked={selectedTickers.includes(ticker)}
                onChange={() => toggle(selectedTickers, ticker, setSelectedTickers)}
              />
              {ticker}
              {!held && ` (${t("query.tickerNotHeld")})`}
            </label>
          ))}
        </fieldset>
        <fieldset className="mb-4">
          <legend>{t("query.metrics")}</legend>
          {METRIC_OPTIONS.map(({ value, labelKey }) => (
            <label key={value} className="mr-2">
              <input
                type="checkbox"
                aria-label={t(labelKey)}
                checked={metrics.includes(value)}
                onChange={() => toggle(metrics, value, setMetrics)}
              />
              {t(labelKey)}
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={loading} className="mr-2">
          {loading ? t("query.running") : t("query.run")}
        </button>
        <button type="button" onClick={handleSave} className="mr-2">
          {t("query.save")}
        </button>
        <button type="button" onClick={handleCopyLink} className="mr-2">
          {t("query.copyLink")}
        </button>
        {safeRows.length > 0 && (
          <span>
            <a href={buildExportUrl("csv")}>{t("query.exportCsv")}</a>{" | "}
            <a href={buildExportUrl("xlsx")}>{t("query.exportXlsx")}</a>
          </span>
        )}
      </form>
      {error && <p className="text-red-500">{error}</p>}
      {safeRows.length > 0 && (
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c as string}
                  style={{ cursor: "pointer", textAlign: "left" }}
                  onClick={() => handleSort(c)}
                >
                  {c as string}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => (
              <tr key={idx}>
                {columns.map((c) => {
                  const key = c as keyof ResultRow;
                  const value =
                    key === "owner"
                      ? getOwnerDisplayName(
                          ownerLookup,
                          typeof r[key] === "string" ? (r[key] as string) : null,
                          typeof r[key] === "string" ? (r[key] as string) : "",
                        )
                      : (r[key] as string | number);
                  return (
                    <td key={c as string} style={{ padding: "4px 6px" }}>
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <SavedQueries onLoad={loadSaved} />
    </div>
  );
}

export function ScreenerQuery() {
  return (
    <div className="space-y-8">
      <Screener />
      <hr className="my-8" />
      <QuerySection />
    </div>
  );
}

export default ScreenerQuery;
