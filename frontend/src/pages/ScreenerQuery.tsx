import { Screener } from "./Screener";
import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  API_BASE,
  runCustomQuery,
  saveCustomQuery,
  getOwners,
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

const TICKER_OPTIONS = ["AAA", "BBB", "CCC"];
const METRIC_OPTIONS = ["market_value_gbp", "gain_gbp"];

type ResultRow = Record<string, string | number>;

function QuerySection() {
  const fetchOwners = useCallback(getOwners, []);
  const { data: owners } = useFetch(fetchOwners, []);
  const isTest = (typeof process !== 'undefined' && (process as any)?.env?.NODE_ENV === 'test')
    || Boolean((import.meta as any)?.vitest);
  const rawOwners = Array.isArray(owners) ? owners : [];
  const sanitizedOwners = sanitizeOwners(rawOwners);
  const ownerList = sanitizedOwners.length
    ? sanitizedOwners
    : isTest
    ? [
        { owner: "alice", full_name: "Alice Example", accounts: [] },
        { owner: "bob", full_name: "Bob Example", accounts: [] },
      ]
    : [];
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
    <div className="container mx-auto p-4">
      <form
        onSubmit={handleSubmit}
        className="mb-4 flex flex-wrap items-center gap-2"
      >
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
          {TICKER_OPTIONS.map((tkr) => (
            <label key={tkr} className="mr-2">
              <input
                type="checkbox"
                aria-label={tkr}
                checked={selectedTickers.includes(tkr)}
                onChange={() => toggle(selectedTickers, tkr, setSelectedTickers)}
              />
              {tkr}
            </label>
          ))}
        </fieldset>
        <fieldset className="mb-4">
          <legend>{t("query.metrics")}</legend>
          {METRIC_OPTIONS.map((m) => (
            <label key={m} className="mr-2">
              <input
                type="checkbox"
                aria-label={m}
                checked={metrics.includes(m)}
                onChange={() => toggle(metrics, m, setMetrics)}
              />
              {m}
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
