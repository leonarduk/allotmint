import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  listTimeseries,
  refetchTimeseries,
  rebuildTimeseriesCache,
} from "../api";
import type { TimeseriesSummary } from "../types";

export default function DataAdmin() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rows, setRows] = useState<TimeseriesSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTimeseries()
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <p style={{ color: "red" }}>{error}</p>;
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
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Exchange</th>
            <th>Name</th>
            <th>Earliest Date</th>
            <th>Latest Date</th>
            <th>Completeness %</th>
            <th>Latest Source</th>
            <th>Main Source</th>
            <th>Actions</th>
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
              <td>{r.latest_source ? `Source: ${r.latest_source}` : ""}</td>
              <td>{r.main_source ?? ""}</td>
              <td>
                <button
                  type="button"
                  onClick={() => handleRefetch(r.ticker, r.exchange)}
                >
                  Refetch
                </button>
                <button
                  type="button"
                  onClick={() => handleRebuild(r.ticker, r.exchange)}
                  style={{ marginLeft: "0.25rem" }}
                >
                  Rebuild cache
                </button>
                <button
                  type="button"
                  onClick={() => navigate(`/instrument/${r.ticker}`)}
                  style={{ marginLeft: "0.25rem" }}
                >
                  Open instrument
                </button>
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
