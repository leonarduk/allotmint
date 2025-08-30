import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listTimeseries } from "../api";
import type { TimeseriesSummary } from "../types";

export default function DataAdmin() {
  const { t } = useTranslation();
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

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h2>{t("app.modes.dataadmin")}</h2>
      <table>
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
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.ticker}.${r.exchange}`}>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
