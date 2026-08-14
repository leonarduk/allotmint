import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  dedupeDataQualitySeries,
  fixDataQualityBatch,
  fixDataQualityIssue,
  getDataQualityAudit,
  getDataQualityIssues,
  getDataQualityTimeseries,
  undoDataQualityAudit,
  type DataQualityAuditEntry,
  type DataQualityIssue,
} from "../api";
import type { TimeseriesQualityPosition } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import { QualityStatusBadge } from "../components/QualityStatusBadge";
import { getQualityStatus, type QualityStatus } from "../lib/dataQualityStatus";
import { DataQualityDrilldownModal } from "../components/DataQualityDrilldownModal";
import EmptyState from "../components/EmptyState";
import { useConfig } from "../ConfigContext";

type Row = TimeseriesQualityPosition & {
  duplicate_count: number;
  outlier_count: number;
  status: QualityStatus;
};

type TabId = "issues" | "series" | "holdings" | "metadata" | "audit";

const ISSUE_TYPES = [
  "WRONG_EXCHANGE",
  "UNRESOLVED_TICKER",
  "MISSING_SERIES",
  "STALE_SERIES",
  "GAPS",
  "DUPLICATES",
  "OUTLIERS",
  "MISSING_METADATA",
  "TICKER_MISMATCH",
] as const;

/** Holdings-related issue types surfaced by the Holdings tab (#6724). */
const HOLDING_ISSUE_TYPES = ["WRONG_EXCHANGE", "UNRESOLVED_TICKER", "MISSING_SERIES"] as const;

interface IssueFilters {
  type: string;
  severity: string;
  ticker: string;
}

function entityLabel(entity: Record<string, unknown>): string {
  const holding = entity.holding as string | undefined;
  const ticker = entity.ticker as string | undefined;
  const exchange = entity.exchange as string | undefined;
  const owner = entity.owner as string | undefined;
  const account = entity.account as string | undefined;
  const parts: string[] = [];
  if (owner) parts.push(String(owner));
  if (account) parts.push(String(account));
  if (holding) parts.push(holding);
  else if (ticker) parts.push(exchange ? `${ticker}.${exchange}` : ticker);
  return parts.join(" / ") || "—";
}

function IssueTable({
  issues,
  loading,
  error,
  onPreview,
  onFix,
  fixingId,
  fixAllVisible,
  fixingAll,
}: {
  issues: DataQualityIssue[];
  loading: boolean;
  error: string | null;
  onPreview: (issue: DataQualityIssue) => void;
  onFix: (issue: DataQualityIssue) => void;
  fixingId: string | null;
  fixAllVisible: (() => void) | null;
  fixingAll: boolean;
}) {
  const { t } = useTranslation();
  if (loading) return <div>{t("common.loading")}</div>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (issues.length === 0) {
    return <EmptyState message={t("dataQuality.admin.issues.noIssues")} actions={[]} />;
  }
  return (
    <>
      {fixAllVisible && issues.some((i) => i.fixable) && (
        <div className="mb-4">
          <button
            type="button"
            onClick={fixAllVisible}
            disabled={fixingAll}
            aria-label={t("dataQuality.admin.issues.actions.fixAll")}
          >
            {fixingAll
              ? t("dataQuality.admin.issues.actions.fixing")
              : t("dataQuality.admin.issues.actions.fixAllShort")}
          </button>
          <span className="ml-2 text-xs opacity-70">
            {t("dataQuality.admin.issues.actions.backupNote")}
          </span>
        </div>
      )}
      <table className={`${tableStyles.table} mb-4 w-full`}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.type")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.severity")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.entity")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.description")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.suggestedFix")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.issues.columns.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue) => (
            <tr key={issue.id}>
              <td className={tableStyles.cell}>
                <code>{issue.type}</code>
              </td>
              <td className={tableStyles.cell}>
                {t(`dataQuality.admin.issues.severity.${issue.severity}`)}
              </td>
              <td className={tableStyles.cell}>{entityLabel(issue.entity)}</td>
              <td className={tableStyles.cell}>{issue.description}</td>
              <td className={tableStyles.cell}>{issue.suggested_fix}</td>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={() => onPreview(issue)}
                  aria-label={t("dataQuality.admin.issues.actions.preview")}
                >
                  {t("dataQuality.admin.issues.actions.preview")}
                </button>{" "}
                {issue.fixable ? (
                  <button
                    type="button"
                    onClick={() => onFix(issue)}
                    disabled={fixingId === issue.id}
                    aria-label={t("dataQuality.admin.issues.actions.fix")}
                  >
                    {fixingId === issue.id
                      ? t("dataQuality.admin.issues.actions.fixing")
                      : t("dataQuality.admin.issues.actions.fix")}
                  </button>
                ) : (
                  <span className="text-xs opacity-60">
                    {t("dataQuality.admin.issues.actions.notFixable")}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function IssueFiltersBar({
  filters,
  onChange,
}: {
  filters: IssueFilters;
  onChange: (filters: IssueFilters) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <label className="text-sm">
        {t("dataQuality.admin.issues.filters.type")}
        <select
          value={filters.type}
          onChange={(e) => onChange({ ...filters, type: e.target.value })}
          className="ml-2"
        >
          <option value="">{t("dataQuality.admin.issues.filters.allTypes")}</option>
          {ISSUE_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        {t("dataQuality.admin.issues.filters.severity")}
        <select
          value={filters.severity}
          onChange={(e) => onChange({ ...filters, severity: e.target.value })}
          className="ml-2"
        >
          <option value="">{t("dataQuality.admin.issues.filters.allSeverities")}</option>
          <option value="high">{t("dataQuality.admin.issues.severity.high")}</option>
          <option value="medium">{t("dataQuality.admin.issues.severity.medium")}</option>
          <option value="low">{t("dataQuality.admin.issues.severity.low")}</option>
        </select>
      </label>
      <label className="text-sm">
        {t("dataQuality.admin.issues.filters.ticker")}
        <input
          type="text"
          value={filters.ticker}
          onChange={(e) => onChange({ ...filters, ticker: e.target.value })}
          className="ml-2"
          placeholder="ABC.L"
        />
      </label>
    </div>
  );
}

function IssuesTab({ presetTypes }: { presetTypes?: readonly string[] }) {
  const { t } = useTranslation();
  const [issues, setIssues] = useState<DataQualityIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<IssueFilters>({
    type: presetTypes?.length === 1 ? presetTypes[0] : "",
    severity: "",
    ticker: "",
  });
  const [preview, setPreview] = useState<DataQualityIssue | null>(null);
  const [confirming, setConfirming] = useState<DataQualityIssue | null>(null);
  const [fixingId, setFixingId] = useState<string | null>(null);
  const [fixingAll, setFixingAll] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getDataQualityIssues();
      setIssues(res.issues);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    return issues.filter((issue) => {
      if (presetTypes && presetTypes.length > 1 && !presetTypes.includes(issue.type)) {
        return false;
      }
      if (filters.type && issue.type !== filters.type) return false;
      if (filters.severity && issue.severity !== filters.severity) return false;
      if (filters.ticker) {
        const needle = filters.ticker.trim().toUpperCase();
        const haystack = `${String(issue.entity.ticker ?? "")}.${String(issue.entity.exchange ?? "")} ${String(issue.entity.holding ?? "")}`.toUpperCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [issues, filters, presetTypes]);

  const applyFix = useCallback(
    async (issue: DataQualityIssue) => {
      setFixingId(issue.id);
      setMessageError(null);
      setMessage(null);
      try {
        await fixDataQualityIssue(issue.id);
        setMessage(t("dataQuality.admin.issues.actions.applied"));
        await load();
      } catch (e) {
        setMessageError(e instanceof Error ? e.message : String(e));
      } finally {
        setFixingId(null);
        setConfirming(null);
      }
    },
    [load, t],
  );

  const applyBatch = useCallback(async () => {
    const ids = visible.filter((i) => i.fixable).map((i) => i.id);
    if (ids.length === 0) return;
    setFixingAll(true);
    setMessageError(null);
    setMessage(null);
    try {
      const res = await fixDataQualityBatch(ids);
      setMessage(t("dataQuality.admin.issues.actions.batchApplied", { applied: res.applied, total: ids.length }));
      if (res.failed > 0) {
        setMessageError(t("dataQuality.admin.issues.actions.batchFailed", { failed: res.failed }));
      }
      await load();
    } catch (e) {
      setMessageError(e instanceof Error ? e.message : String(e));
    } finally {
      setFixingAll(false);
    }
  }, [visible, load, t]);

  return (
    <div>
      <h2 className="mb-2 text-xl">{t("dataQuality.admin.issues.title")}</h2>
      <p className="mb-4 text-sm opacity-70">{t("dataQuality.admin.issues.subtitle")}</p>
      <IssueFiltersBar filters={filters} onChange={setFilters} />
      {message && <p role="status" className="mb-2 text-green-700">{message}</p>}
      {messageError && <p role="alert" className="mb-2 text-red-700">{messageError}</p>}
      <IssueTable
        issues={visible}
        loading={loading}
        error={error}
        onPreview={setPreview}
        onFix={(issue) => setConfirming(issue)}
        fixingId={fixingId}
        fixAllVisible={visible.some((i) => i.fixable) ? applyBatch : null}
        fixingAll={fixingAll}
      />

      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setPreview(null)}
        >
          <div className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-6 text-slate-900"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-2 text-lg font-semibold">
              {t("dataQuality.admin.issues.previewTitle", { type: preview.type })}
            </h3>
            <p className="mb-4 text-sm">{preview.description}</p>
            <div className="mb-4 grid grid-cols-2 gap-4">
              <div>
                <h4 className="mb-1 text-sm font-semibold">{t("dataQuality.admin.issues.before")}</h4>
                <pre className="overflow-auto rounded bg-gray-100 p-2 text-xs">{JSON.stringify(preview.preview.before ?? {}, null, 2)}</pre>
              </div>
              <div>
                <h4 className="mb-1 text-sm font-semibold">{t("dataQuality.admin.issues.after")}</h4>
                <pre className="overflow-auto rounded bg-gray-100 p-2 text-xs">{JSON.stringify(preview.preview.after ?? {}, null, 2)}</pre>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setPreview(null)}>
                {t("dataQuality.admin.issues.actions.close")}
              </button>
              {preview.fixable && (
                <button type="button" onClick={() => { setConfirming(preview); setPreview(null); }}>
                  {t("dataQuality.admin.issues.actions.apply")}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setConfirming(null)}
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 text-slate-900"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-2 text-lg font-semibold">
              {t("dataQuality.admin.issues.actions.confirmTitle")}
            </h3>
            <p className="mb-2 text-sm">{confirming.suggested_fix}</p>
            <p className="mb-4 text-xs opacity-70">{t("dataQuality.admin.issues.actions.confirmBody")}</p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirming(null)}>
                {t("dataQuality.admin.issues.actions.cancel")}
              </button>
              <button type="button" onClick={() => applyFix(confirming)} disabled={fixingId === confirming.id}>
                {fixingId === confirming.id
                  ? t("dataQuality.admin.issues.actions.fixing")
                  : t("dataQuality.admin.issues.actions.apply")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SeriesTab() {
  const { t } = useTranslation();
  const [positions, setPositions] = useState<TimeseriesQualityPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TimeseriesQualityPosition | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getDataQualityTimeseries();
      setPositions(res.positions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows: Row[] = useMemo(
    () =>
      positions.map((p) => ({
        ...p,
        duplicate_count: p.duplicate_dates.length,
        outlier_count: p.outliers.length,
        status: getQualityStatus(p),
      })),
    [positions],
  );

  const { sorted, sortKey, asc, handleSort } = useSortableTable(rows, "ticker");

  const handleDedupe = async (row: Row) => {
    setBusyKey(`dedupe:${row.ticker}.${row.exchange}`);
    setMessage(null);
    try {
      const res = await dedupeDataQualitySeries(row.ticker, row.exchange);
      setMessage(t("dataQuality.admin.series.deduped", { removed: res.removed ?? 0 }));
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div>
      <h2 className="mb-2 text-xl">{t("dataQuality.admin.series.title")}</h2>
      {message && <p role="status" className="mb-2 text-green-700">{message}</p>}
      {loading && <div>{t("common.loading")}</div>}
      {error && <p style={{ color: "red" }}>{error}</p>}
      {!loading && !error && sorted.length === 0 && (
        <EmptyState message={t("dataQuality.noData")} actions={[]} />
      )}
      {!loading && !error && sorted.length > 0 && (
        <table className={`${tableStyles.table} mb-4 w-full`}>
          <thead>
            <tr>
              <th
                className={`${tableStyles.cell} ${tableStyles.clickable}`}
                onClick={() => handleSort("ticker")}
              >
                {t("dataQuality.columns.ticker")}
                {sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
              </th>
              <th className={tableStyles.cell}>{t("dataQuality.columns.exchange")}</th>
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("total_points")}
              >
                {t("dataQuality.columns.totalPoints")}
                {sortKey === "total_points" ? (asc ? " ▲" : " ▼") : ""}
              </th>
              <th className={tableStyles.cell}>{t("dataQuality.columns.dateRange")}</th>
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("gap_count")}
              >
                {t("dataQuality.columns.gapCount")}
                {sortKey === "gap_count" ? (asc ? " ▲" : " ▼") : ""}
              </th>
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("duplicate_count")}
              >
                {t("dataQuality.columns.duplicateCount")}
                {sortKey === "duplicate_count" ? (asc ? " ▲" : " ▼") : ""}
              </th>
              <th
                className={`${tableStyles.cell} ${tableStyles.right} ${tableStyles.clickable}`}
                onClick={() => handleSort("outlier_count")}
              >
                {t("dataQuality.columns.outlierCount")}
                {sortKey === "outlier_count" ? (asc ? " ▲" : " ▼") : ""}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.center}`}>
                {t("dataQuality.columns.status")}
              </th>
              <th className={tableStyles.cell}></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={`${row.ticker}.${row.exchange}`}>
                <td className={tableStyles.cell}>{row.ticker}</td>
                <td className={tableStyles.cell}>{row.exchange}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{row.total_points}</td>
                <td className={tableStyles.cell}>
                  {row.first_date && row.last_date
                    ? `${row.first_date} – ${row.last_date}`
                    : "—"}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{row.gap_count}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{row.duplicate_count}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{row.outlier_count}</td>
                <td className={`${tableStyles.cell} ${tableStyles.center}`}>
                  <QualityStatusBadge status={row.status} />
                </td>
                <td className={tableStyles.cell}>
                  <button
                    type="button"
                    onClick={() => handleDedupe(row)}
                    disabled={busyKey === `dedupe:${row.ticker}.${row.exchange}`}
                    aria-label={t("dataQuality.admin.series.dedupe")}
                  >
                    {busyKey === `dedupe:${row.ticker}.${row.exchange}`
                      ? "…"
                      : t("dataQuality.admin.series.dedupe")}
                  </button>{" "}
                  <button
                    type="button"
                    onClick={() => setSelected(row)}
                    aria-label={t("dataQuality.viewDetailsFor", {
                      ticker: row.ticker,
                      exchange: row.exchange,
                    })}
                  >
                    {t("dataQuality.viewDetails")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <DataQualityDrilldownModal position={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function AuditTab() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<DataQualityAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [undoingId, setUndoingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getDataQualityAudit();
      setEntries(res.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleUndo = async (entryId: string) => {
    setUndoingId(entryId);
    setMessage(null);
    setMessageError(null);
    try {
      await undoDataQualityAudit(entryId);
      setMessage(t("dataQuality.admin.audit.actions.undone"));
      await load();
    } catch (e) {
      setMessageError(
        t("dataQuality.admin.audit.actions.undoFailed", {
          detail: e instanceof Error ? e.message : String(e),
        }),
      );
    } finally {
      setUndoingId(null);
    }
  };

  if (loading) return <div>{t("common.loading")}</div>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (entries.length === 0) {
    return <EmptyState message={t("dataQuality.admin.audit.empty")} actions={[]} />;
  }

  return (
    <div>
      <h2 className="mb-2 text-xl">{t("dataQuality.admin.audit.title")}</h2>
      {message && <p role="status" className="mb-2 text-green-700">{message}</p>}
      {messageError && <p role="alert" className="mb-2 text-red-700">{messageError}</p>}
      <table className={`${tableStyles.table} mb-4 w-full`}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.timestamp")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.action")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.entity")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.before")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.after")}</th>
            <th className={tableStyles.cell}>{t("dataQuality.admin.audit.columns.actor")}</th>
            <th className={tableStyles.cell}></th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td className={tableStyles.cell}>
                {new Date(entry.timestamp).toLocaleString()}
              </td>
              <td className={tableStyles.cell}>{entry.action}</td>
              <td className={tableStyles.cell}>{entityLabel(entry.entity)}</td>
              <td className={tableStyles.cell}>
                <pre className="text-xs">{JSON.stringify(entry.before)}</pre>
              </td>
              <td className={tableStyles.cell}>
                <pre className="text-xs">{JSON.stringify(entry.after)}</pre>
              </td>
              <td className={tableStyles.cell}>{entry.actor ?? "—"}</td>
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  onClick={() => handleUndo(entry.id)}
                  disabled={undoingId === entry.id}
                  aria-label={t("dataQuality.admin.audit.actions.undo")}
                >
                  {undoingId === entry.id ? "…" : t("dataQuality.admin.audit.actions.undo")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetadataTab() {
  const { t } = useTranslation();
  return (
    <div>
      <h2 className="mb-2 text-xl">{t("dataQuality.admin.metadata.title")}</h2>
      <p className="mb-4 text-sm opacity-70">{t("dataQuality.admin.metadata.note")}</p>
      <a href="/instrumentadmin" className="underline">
        {t("dataQuality.admin.metadata.openInstrumentAdmin")}
      </a>
    </div>
  );
}

export default function DataQuality() {
  const { t } = useTranslation();
  const { dataQualityAdmin } = useConfig();
  const [tab, setTab] = useState<TabId>(dataQualityAdmin === false ? "series" : "issues");

  if (dataQualityAdmin === false) {
    // Read-only fallback: keep the original series table available when the
    // admin surface is disabled by configuration (#6724).
    return (
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "1rem" }}>
        <h1>{t("dataQuality.title")}</h1>
        <SeriesTab />
      </div>
    );
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "issues", label: t("dataQuality.admin.tabs.issues") },
    { id: "series", label: t("dataQuality.admin.tabs.series") },
    { id: "holdings", label: t("dataQuality.admin.tabs.holdings") },
    { id: "metadata", label: t("dataQuality.admin.tabs.metadata") },
    { id: "audit", label: t("dataQuality.admin.tabs.audit") },
  ];

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "1rem" }}>
      <h1>{t("dataQuality.title")}</h1>
      <nav role="tablist" aria-label="Data quality admin" className="mb-4 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={tab === item.id ? "rounded bg-blue-700 px-3 py-1 text-white" : "rounded bg-gray-200 px-3 py-1"}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {tab === "issues" && <IssuesTab />}
      {tab === "series" && <SeriesTab />}
      {tab === "holdings" && <IssuesTab presetTypes={HOLDING_ISSUE_TYPES} />}
      {tab === "metadata" && <MetadataTab />}
      {tab === "audit" && <AuditTab />}
    </div>
  );
}
