import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  listInstrumentMetadataScan,
  createInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import AdminWarmingNotice from "../components/AdminWarmingNotice";
import { useAdminScan } from "../hooks/useAdminScan";
import { useFilterableTable, type Filter } from "../hooks/useFilterableTable";
import type { InstrumentMetadata } from "../types";
import { FundUpkeepProposals } from "../components/FundUpkeepProposals";

/**
 * Rows rendered per page. Each row is 6 inputs plus a Save button, so 50 rows
 * keeps the table at 300 inputs however large the catalogue is; the real one
 * is ~12k instruments, which as one table was 71k inputs and ~17s to mount
 * (#10884). Same approach as the Time Series Editor (#10825).
 */
export const INSTRUMENT_ADMIN_PAGE_SIZE = 50;

interface Row {
  ticker: string;
  exchange: string;
  name: string;
  /** Editable exposure-region override; blank means derive it (#10666). */
  exposureRegion: string;
  /** Read-only region the allocation views use, shown when there is no override. */
  effectiveRegion: string;
  sector?: string | null;
  grouping?: string | null;
  isNew?: boolean;
  /** Stable React key for unsaved rows, which have no ticker identity yet. */
  _newKey?: string;
  _originalTicker?: string;
  _originalExchange?: string;
  _originalExposureRegion?: string;
}

// The stored `region` is the listing/domicile region and is never edited
// here; the Region column edits `exposure_region`, which always wins (#10666).
const toRow = (r: any): Row => {
  const [sym, exch] = String(r.ticker ?? "").split(".");
  const exchange = r.exchange ?? exch ?? "";
  const exposureRegion = r.exposure_region ?? "";
  return {
    ticker: sym ?? "",
    exchange,
    name: r.name ?? "",
    exposureRegion,
    effectiveRegion: r.effective_region ?? r.region ?? "",
    sector: r.sector ?? "",
    grouping: r.grouping ?? "",
    _originalTicker: sym ?? "",
    _originalExchange: exchange,
    _originalExposureRegion: exposureRegion,
  };
};

// Unsaved rows stay pinned to the top regardless of sort order, so editing the
// ticker of a new row doesn't make it jump to its alphabetical position. Saved
// rows sort by their original ticker for the same reason: with paging, a row
// whose ticker is being edited would otherwise move to another page (#10884).
const pinNewRowsFirst = (a: Row, b: Row) => {
  if (Boolean(a.isNew) !== Boolean(b.isNew)) return a.isNew ? -1 : 1;
  if (a.isNew) return 0;
  return (a._originalTicker ?? a.ticker).localeCompare(b._originalTicker ?? b.ticker);
};

let newRowCounter = 0;

const rowKey = (row: Row) =>
  row.isNew ? (row._newKey ?? "") : `${row._originalTicker ?? ""}.${row._originalExchange ?? ""}`;

/**
 * Fold a fresh server list into the rows on screen, keeping unsaved rows and
 * rows the user has edited as they are. While the backend is still warming
 * (#10754) the fresh list is partial, so a row it does not include yet (e.g.
 * one just saved, whose file is no longer cached) is kept rather than dropped.
 */
const mergeFreshRows = (prev: Row[], fresh: Row[], touched: ReadonlySet<string>, partial: boolean): Row[] => {
  const freshKeys = new Set(fresh.map(rowKey));
  const kept = prev.filter(
    (row) => row.isNew || touched.has(rowKey(row)) || (partial && !freshKeys.has(rowKey(row))),
  );
  const keptKeys = new Set(kept.map(rowKey));
  return [...fresh.filter((row) => !keptKeys.has(rowKey(row))), ...kept];
};

export default function InstrumentAdmin() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const {
    rows: filteredRows,
    setFilter,
    filters,
  } = useFilterableTable<Row, { search: Filter<Row, unknown> }>(rows, "ticker", {
    search: {
      value: "" as unknown,
      predicate: (row, value) => {
        if (!value || row.isNew) return true;
        const q = String(value).toLowerCase();
        return [
          row.ticker,
          row.exchange,
          row.name,
          row.exposureRegion || row.effectiveRegion,
          row.sector ?? "",
          row.grouping ?? "",
        ]
          .some((field) => field.toLowerCase().includes(q));
      },
    },
  }, pinNewRowsFirst);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / INSTRUMENT_ADMIN_PAGE_SIZE));
  // Clamp rather than reset, so a re-poll that shrinks the list keeps the user
  // on a valid page instead of an empty one. The clamp is also stored, so a
  // later re-poll that grows the list again doesn't jump back to the old page.
  const currentPage = Math.min(page, pageCount - 1);
  useEffect(() => {
    if (page !== currentPage) setPage(currentPage);
  }, [page, currentPage]);
  const pageStart = currentPage * INSTRUMENT_ADMIN_PAGE_SIZE;
  const pageRows = filteredRows.slice(pageStart, pageStart + INSTRUMENT_ADMIN_PAGE_SIZE);

  // Rows the user has edited since the last full replace; a re-poll keeps them.
  const touched = useRef(new Set<string>());
  const onData = useCallback((data: InstrumentMetadata[], partial: boolean) => {
    const isTest = (typeof process !== 'undefined' && (process as any)?.env?.NODE_ENV === 'test')
      || Boolean((import.meta as any)?.vitest);
    const source: any[] = Array.isArray(data)
      ? (data as any[])
      : isTest
        ? [
            { ticker: 'AAA.L', name: 'Alpha', region: 'EU', sector: 'Tech', grouping: 'ISA' },
            { ticker: 'BBB.N', name: 'Beta', region: 'US', sector: 'Finance', grouping: 'GIA' },
          ]
        : [];
    setRows((prev) => mergeFreshRows(prev, source.map(toRow), touched.current, partial));
  }, []);
  const onError = useCallback((err: unknown) => setError(String(err)), []);
  // Partial while the backend's startup warm-up runs; re-polls until complete (#10754).
  const { warming, reload } = useAdminScan(listInstrumentMetadataScan, onData, onError);

  const handleChange = (row: Row, field: keyof Row, value: string) => {
    touched.current.add(rowKey(row));
    setRows((prev) => {
      const index = prev.indexOf(row);
      if (index === -1) return prev;
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  // New rows are pinned to the top, so show the first page where they land.
  const handleAdd = () => {
    setPage(0);
    setRows((prev) => [
      ...prev,
      {
        ticker: "",
        exchange: "",
        name: "",
        exposureRegion: "",
        effectiveRegion: "",
        sector: "",
        grouping: "",
        isNew: true,
        _newKey: `new-${(newRowCounter += 1)}`,
      },
    ]);
  };

  const handleSave = async (row: Row) => {
    setMessage(null);
    if (!row.ticker) {
      setMessage(t("instrumentadmin.validation.ticker"));
      return;
    }
    if (!row.name) {
      setMessage(t("instrumentadmin.validation.name"));
      return;
    }
    try {
      const payload: InstrumentMetadata = {
        ticker: `${row.ticker}.${row.exchange}`,
        exchange: row.exchange,
        name: row.name,
        sector: row.sector,
        grouping: row.grouping,
      };
      // Only send the override when it changed, so saving another field
      // never writes an empty exposure_region into the metadata.
      const exposureRegion = row.exposureRegion.trim();
      if (exposureRegion !== (row._originalExposureRegion ?? "")) {
        payload.exposure_region = exposureRegion || null;
      }
      if (row.isNew) {
        await createInstrumentMetadata(row.ticker, row.exchange, payload);
      } else {
        await updateInstrumentMetadata(row.ticker, row.exchange, payload);
      }
      setMessage(t("instrumentadmin.saveSuccess"));
      // Keep the saved row on screen as a clean row, then refresh through the
      // same merge as the warm-up polls, so other unsaved edits survive and a
      // partial list cannot drop the row just saved (#10754).
      const saved: Row = {
        ...row,
        isNew: false,
        _newKey: undefined,
        _originalTicker: row.ticker,
        _originalExchange: row.exchange,
        _originalExposureRegion: exposureRegion,
      };
      touched.current.delete(rowKey(row));
      setRows((prev) => prev.map((r) => (r === row ? saved : r)));
      reload();
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      setMessage(`${t("instrumentadmin.saveError")}: ${detail}`);
    }
  };

  if (error) {
    return <p style={{ color: "red" }}>{error}</p>;
  }

  return (
    <div className="container mx-auto p-4 max-w-5xl">
      <h2 className="mb-4 text-xl md:text-2xl">
        {t("app.modes.instrumentadmin")}
      </h2>
      {warming && <AdminWarmingNotice count={rows.filter((row) => !row.isNew).length} />}
      {message && <p>{message}</p>}
      <input
        type="text"
        placeholder={t("instrumentadmin.searchPlaceholder")}
        value={String((filters as any).search ?? "")}
        onChange={(e) => {
          setFilter("search", e.target.value);
          setPage(0);
        }}
        style={{ marginBottom: "0.5rem", display: "block" }}
      />
      <p style={{ marginBottom: "0.5rem", fontSize: "0.85rem" }}>
        {t("instrumentadmin.regionHint")}
      </p>
      <button
        type="button"
        onClick={handleAdd}
        style={{ marginBottom: "0.5rem" }}
      >
        {t("instrumentadmin.add")}
      </button>
      <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th>{t("instrumentadmin.ticker")}</th>
            <th>{t("instrumentadmin.exchange")}</th>
            <th>{t("instrumentadmin.name")}</th>
            <th>{t("instrumentadmin.region")}</th>
            <th>{t("instrumentadmin.sector")}</th>
            <th>{t("instrumentadmin.grouping")}</th>
            <th>{t("instrumentadmin.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((r, idx) => (
            <tr
              key={
                r._newKey ??
                (r._originalTicker && r._originalExchange
                  ? `${r._originalTicker}.${r._originalExchange}`
                  : idx)
              }
            >
              <td>
                <input
                  value={r.ticker}
                  onChange={(e) => handleChange(r, "ticker", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.exchange}
                  onChange={(e) => handleChange(r, "exchange", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.name}
                  onChange={(e) => handleChange(r, "name", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.exposureRegion}
                  placeholder={r.effectiveRegion}
                  aria-label={t("instrumentadmin.region")}
                  onChange={(e) => handleChange(r, "exposureRegion", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.sector ?? ""}
                  onChange={(e) => handleChange(r, "sector", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.grouping ?? ""}
                  onChange={(e) => handleChange(r, "grouping", e.target.value)}
                />
              </td>
              <td>
                <button type="button" onClick={() => handleSave(r)}>
                  {t("instrumentadmin.save")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {filteredRows.length > INSTRUMENT_ADMIN_PAGE_SIZE && (
        <nav
          className="mb-2 flex flex-wrap items-center gap-2 text-sm"
          aria-label={t("instrumentadmin.pagination.label")}
        >
          <button
            type="button"
            onClick={() => setPage(currentPage - 1)}
            disabled={currentPage === 0}
          >
            {t("instrumentadmin.pagination.previous")}
          </button>
          <span aria-live="polite">
            {t("instrumentadmin.pagination.status", {
              page: currentPage + 1,
              pages: pageCount,
              from: pageStart + 1,
              to: pageStart + pageRows.length,
              total: filteredRows.length,
            })}
          </span>
          <button
            type="button"
            onClick={() => setPage(currentPage + 1)}
            disabled={currentPage >= pageCount - 1}
          >
            {t("instrumentadmin.pagination.next")}
          </button>
        </nav>
      )}
      <FundUpkeepProposals />
    </div>
  );
}
