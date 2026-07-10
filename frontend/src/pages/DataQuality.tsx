import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { getDataQualityTimeseries } from "../api";
import type { TimeseriesQualityPosition } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import tableStyles from "../styles/table.module.css";
import { QualityStatusBadge } from "../components/QualityStatusBadge";
import { getQualityStatus, type QualityStatus } from "../lib/dataQualityStatus";
import { DataQualityDrilldownModal } from "../components/DataQualityDrilldownModal";
import EmptyState from "../components/EmptyState";

type Row = TimeseriesQualityPosition & {
  duplicate_count: number;
  outlier_count: number;
  status: QualityStatus;
};

export default function DataQuality() {
  const { t } = useTranslation();
  const [positions, setPositions] = useState<TimeseriesQualityPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TimeseriesQualityPosition | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDataQualityTimeseries()
      .then((res) => {
        if (cancelled) return;
        setPositions(res.positions);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setPositions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "1rem" }}>
      <h1>{t("dataQuality.title")}</h1>

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
                  <button type="button" onClick={() => setSelected(row)}>
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
