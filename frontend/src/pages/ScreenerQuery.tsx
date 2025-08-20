import {Screener} from "./Screener";
import {useState, useCallback} from "react";
import {useTranslation} from "react-i18next";
import {API_BASE, runCustomQuery, saveCustomQuery, getOwners} from "../api";
import type {CustomQuery} from "../types";
import {useFetch} from "../hooks/useFetch";
import {useSortableTable} from "../hooks/useSortableTable";
import {SavedQueries} from "../components/SavedQueries";

const TICKER_OPTIONS = ["AAA", "BBB", "CCC"];
const METRIC_OPTIONS = ["market_value_gbp", "gain_gbp"];

type ResultRow = Record<string, string | number>;

function QuerySection() {
  const fetchOwners = useCallback(getOwners, []);
  const {data: owners} = useFetch(fetchOwners, []);
  const {t} = useTranslation();

  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selectedOwners, setSelectedOwners] = useState<string[]>([]);
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const columns = rows.length
    ? (Object.keys(rows[0]) as (keyof ResultRow)[])
    : [];
  const {sorted, handleSort} = useSortableTable<ResultRow>(
    rows,
    (columns[0] as keyof ResultRow) || ("owner" as keyof ResultRow)
  );

  function toggle(
    list: string[],
    value: string,
    setter: (v: string[]) => void
  ) {
    setter(
      list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
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
    <div>
      <form onSubmit={handleSubmit} style={{marginBottom: "1rem"}}>
        <label style={{marginRight: "0.5rem"}}>
          {t("query.start")}
          <input
            aria-label={t("query.start")}
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            style={{marginLeft: "0.25rem"}}
          />
        </label>
        <label style={{marginRight: "0.5rem"}}>
          {t("query.end")}
          <input
            aria-label={t("query.end")}
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            style={{marginLeft: "0.25rem"}}
          />
        </label>
        <fieldset style={{marginBottom: "1rem"}}>
          <legend>{t("query.owners")}</legend>
          {owners?.map((o) => (
            <label key={o.owner} style={{marginRight: "0.5rem"}}>
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
        <fieldset style={{marginBottom: "1rem"}}>
          <legend>{t("query.tickers")}</legend>
          {TICKER_OPTIONS.map((tkr) => (
            <label key={tkr} style={{marginRight: "0.5rem"}}>
              <input
                type="checkbox"
                aria-label={tkr}
                checked={selectedTickers.includes(tkr)}
                onChange={() =>
                  toggle(selectedTickers, tkr, setSelectedTickers)
                }
              />
              {tkr}
            </label>
          ))}
        </fieldset>
        <fieldset style={{marginBottom: "1rem"}}>
          <legend>{t("query.metrics")}</legend>
          {METRIC_OPTIONS.map((m) => (
            <label key={m} style={{marginRight: "0.5rem"}}>
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
        <button
          type="submit"
          disabled={loading}
          style={{marginRight: "0.5rem"}}
        >
          {loading ? t("query.running") : t("query.run")}
        </button>
        <button
          type="button"
          onClick={handleSave}
          style={{marginRight: "0.5rem"}}
        >
          {t("query.save")}
        </button>
        {rows.length > 0 && (
          <span>
            <a href={buildExportUrl("csv")}>{t("query.exportCsv")}</a>
            {" | "}
            <a href={buildExportUrl("xlsx")}>{t("query.exportXlsx")}</a>
          </span>
        )}
      </form>
      {error && <p style={{color: "red"}}>{error}</p>}
      {rows.length > 0 && (
        <table style={{width: "100%", borderCollapse: "collapse"}}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c as string}
                  style={{cursor: "pointer", textAlign: "left"}}
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
                {columns.map((c) => (
                  <td key={c as string} style={{padding: "4px 6px"}}>
                    {r[c] as string | number}
                  </td>
                ))}
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
    <div>
      <Screener />
      <hr style={{margin: "2rem 0"}} />
      <QuerySection />
    </div>
  );
}

export default ScreenerQuery;
