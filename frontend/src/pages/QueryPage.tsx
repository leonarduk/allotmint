import { useEffect, useState } from "react";
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

const TICKER_OPTIONS = ["AAA", "BBB", "CCC"];
const METRIC_OPTIONS = ["market_value_gbp", "gain_gbp"];

type ResultRow = Record<string, string | number>;

export function QueryPage() {
  const { data: owners } = useFetch(() => getOwners(), []);
  const { t } = useTranslation();

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selectedOwners, setSelectedOwners] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [columns, setColumns] = useState<(keyof ResultRow)[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<(keyof ResultRow)[]>([]);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const columns = rows.length ? (Object.keys(rows[0]) as (keyof ResultRow)[]) : [];
  const {
    sorted,
    sortKey,
    asc,
    handleSort,
    setSortKey,
    setAsc,
  } = useSortableTable<ResultRow, keyof ResultRow>(
    rows,
    (columns[0] as keyof ResultRow) || ("owner" as keyof ResultRow),
  );

  useEffect(() => {
    const cols = rows.length
      ? (Object.keys(rows[0]) as (keyof ResultRow)[])
      : [];
    setColumns(cols);
    setVisibleColumns((prev) =>
      prev.length ? prev.filter((c) => cols.includes(c)) : cols,
    );
    if (cols.length && !cols.includes(sortKey)) {
      setSortKey(cols[0] as keyof ResultRow);
    }
    setPage(1);
  }, [rows, sortKey, setSortKey]);

  function toggle<T>(list: T[], value: T, setter: (v: T[]) => void) {
    setter(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const params: CustomQuery = {
      start,
      end,
      owners: selectedOwners,
      tickers: selectedTickers,
      metrics,
      columns: visibleColumns as string[],
      sortKey: sortKey as string,
      sortAsc: asc,
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
      columns: visibleColumns as string[],
      sortKey: sortKey as string,
      sortAsc: asc,
    };
    void saveCustomQuery(name, params);
  }

  function loadSaved(params: CustomQuery) {
    setStart(params.start ?? "");
    setEnd(params.end ?? "");
    setSelectedOwners(params.owners ?? []);
    setSelectedTickers(params.tickers ?? []);
    setMetrics(params.metrics ?? []);
    setVisibleColumns((params.columns as (keyof ResultRow)[]) ?? []);
    if (params.sortKey) setSortKey(params.sortKey as keyof ResultRow);
    if (params.sortAsc != null) setAsc(params.sortAsc);
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
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          {t("query.start")}
          <input
            aria-label={t("query.start")}
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("query.end")}
          <input
            aria-label={t("query.end")}
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <fieldset style={{ marginBottom: "1rem" }}>
          <legend>{t("query.owners")}</legend>
          {owners?.map((o) => (
            <label key={o.owner} style={{ marginRight: "0.5rem" }}>
              <input
                type="checkbox"
                aria-label={o.owner}
                checked={selectedOwners.includes(o.owner)}
                onChange={() =>
                  toggle(selectedOwners, o.owner, setSelectedOwners)
                }
              />
              {o.owner}
            </label>
          ))}
        </fieldset>
        <fieldset style={{ marginBottom: "1rem" }}>
          <legend>{t("query.tickers")}</legend>
          {TICKER_OPTIONS.map((t) => (
            <label key={t} style={{ marginRight: "0.5rem" }}>
              <input
                type="checkbox"
                aria-label={t}
                checked={selectedTickers.includes(t)}
                onChange={() =>
                  toggle(selectedTickers, t, setSelectedTickers)
                }
              />
              {t}
            </label>
          ))}
        </fieldset>
        <fieldset style={{ marginBottom: "1rem" }}>
          <legend>{t("query.metrics")}</legend>
          {METRIC_OPTIONS.map((m) => (
            <label key={m} style={{ marginRight: "0.5rem" }}>
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
        <button type="submit" disabled={loading} style={{ marginRight: "0.5rem" }}>
          {loading ? t("query.running") : t("query.run")}
        </button>
        <button type="button" onClick={handleSave} style={{ marginRight: "0.5rem" }}>
          {t("query.save")}
        </button>
        {rows.length > 0 && (
          <span>
            <a href={buildExportUrl("csv")}>{t("query.exportCsv")}</a>{" | "}
            <a href={buildExportUrl("xlsx")}>{t("query.exportXlsx")}</a>
          </span>
        )}
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {rows.length > 0 && (
        <>
          <fieldset style={{ marginBottom: "1rem" }}>
            <legend>Columns</legend>
            {columns.map((c) => (
              <label key={c as string} style={{ marginRight: "0.5rem" }}>
                <input
                  type="checkbox"
                  aria-label={c as string}
                  checked={visibleColumns.includes(c)}
                  onChange={() =>
                    toggle(visibleColumns, c, setVisibleColumns)
                  }
                />
                {c as string}
              </label>
            ))}
          </fieldset>
          <div style={{ marginBottom: "0.5rem" }}>
            <label>
              Filter
              <input
                aria-label="Filter"
                type="text"
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(1);
                }}
                style={{ marginLeft: "0.25rem" }}
              />
            </label>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {visibleColumns.map((c) => (
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
              {(() => {
                const filtered = sorted.filter((r) =>
                  filter
                    ? columns.some((c) =>
                        String(r[c] ?? "")
                          .toLowerCase()
                          .includes(filter.toLowerCase()),
                      )
                    : true,
                );
                const pageCount = Math.ceil(filtered.length / pageSize) || 1;
                const startIdx = (page - 1) * pageSize;
                const pageRows = filtered.slice(startIdx, startIdx + pageSize);
                return (
                  <>
                    {pageRows.map((r, idx) => (
                      <tr key={idx}>
                        {visibleColumns.map((c) => (
                          <td key={c as string} style={{ padding: "4px 6px" }}>
                            {r[c] as string | number}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {pageCount > 1 && (
                      <tr>
                        <td colSpan={visibleColumns.length}>
                          <div style={{ marginTop: "0.5rem" }}>
                            <button
                              onClick={() => setPage((p) => Math.max(1, p - 1))}
                              disabled={page === 1}
                              style={{ marginRight: "0.5rem" }}
                            >
                              Prev
                            </button>
                            <span>
                              Page {page} of {pageCount}
                            </span>
                            <button
                              onClick={() =>
                                setPage((p) => Math.min(pageCount, p + 1))
                              }
                              disabled={page === pageCount}
                              style={{ marginLeft: "0.5rem" }}
                            >
                              Next
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })()}
            </tbody>
          </table>
        </>
      )}
      <SavedQueries onLoad={loadSaved} />
    </div>
  );
}

export default QueryPage;
