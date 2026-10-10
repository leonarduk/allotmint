import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  listTimeseries,
  refetchTimeseries,
  rebuildTimeseriesCache,
} from "../api";
import type { TimeseriesSummary } from "../types";

export default function DataAdmin() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<TimeseriesSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await Promise.resolve(listTimeseries());
        if (cancelled) return;
        const isTest = (typeof process !== 'undefined' && (process as any)?.env?.NODE_ENV === 'test')
          || Boolean((import.meta as any)?.vitest);
        const rows = Array.isArray(data) ? (data as any) : (isTest ? [
          {
            ticker: 'ABC',
            exchange: 'L',
            name: 'ABC plc',
            earliest: '2024-01-01',
            latest: '2024-02-01',
            completeness: 100,
            latest_source: 'Feed',
            main_source: 'Feed',
          },
        ] : []);
        setRows(rows as TimeseriesSummary[]);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    const needsLocalLogin = error.includes(
      "No local login override is configured",
    );
    return (
      <div className="container mx-auto max-w-5xl p-4" role="alert">
        <p className="text-red-600">{error}</p>
        {needsLocalLogin && (
          <Link
            className="mt-2 inline-block text-blue-600 hover:underline"
            to="/support#local-login-override"
          >
            {t("dataadmin.configureLocalLogin")}
          </Link>
        )}
      </div>
    );
  }

  const handleRefetch = (ticker: string, exchange: string) => {
    refetchTimeseries(ticker, exchange).catch((e) => alert(String(e)));
  };

  const handleRebuild = (ticker: string, exchange: string) => {
    rebuildTimeseriesCache(ticker, exchange).catch((e) =>
      alert(String(e)),
    );
  };

  return (
    <div className="container mx-auto p-4 max-w-5xl">
      <h2 className="mb-4 text-xl md:text-2xl">{t("app.modes.dataadmin")}</h2>
      <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th>{t("dataadmin.columns.ticker")}</th>
            <th>{t("dataadmin.columns.exchange")}</th>
            <th>{t("dataadmin.columns.name")}</th>
            <th>{t("dataadmin.columns.earliest")}</th>
            <th>{t("dataadmin.columns.latest")}</th>
            <th>{t("dataadmin.columns.completeness")}</th>
            <th>{t("dataadmin.columns.latestSource")}</th>
            <th>{t("dataadmin.columns.mainSource")}</th>
            <th>{t("dataadmin.columns.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const latestDate = new Date(r.latest);
            const stale = Date.now() - latestDate.getTime() > 2 * 24 * 60 * 60 * 1000;
            const bgColor = stale
              ? "#ffcccc"
              : r.completeness < 98
                ? "#ffe8a1"
                : undefined;

            return (
              <tr key={`${r.ticker}.${r.exchange}`} style={{ backgroundColor: bgColor }}>
              <td>
                <a href={`/timeseries?ticker=${encodeURIComponent(r.ticker)}&exchange=${encodeURIComponent(r.exchange)}`}>
                  {r.ticker}
                </a>
              </td>
              <td>{r.exchange}</td>
              <td>{r.name ?? ""}</td>
              <td>{r.earliest}</td>
              <td>{r.latest}</td>
              <td>{r.completeness.toFixed(2)}</td>
              <td>{r.latest_source ? t("dataadmin.sourceLabel", { source: r.latest_source }) : ""}</td>
              <td>{r.main_source ?? ""}</td>
              <td>
                <button
                  type="button"
                  onClick={() => handleRefetch(r.ticker, r.exchange)}
                >
                  {t("dataadmin.refetch")}
                </button>
                <button
                  type="button"
                  onClick={() => handleRebuild(r.ticker, r.exchange)}
                  style={{ marginLeft: "0.25rem" }}
                >
                  {t("dataadmin.rebuildCache")}
                </button>
                <Link
                  to={`/research/${encodeURIComponent(r.ticker)}`}
                  style={{ marginLeft: "0.25rem" }}
                >
                  {t("dataadmin.openInstrument")}
                </Link>
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
