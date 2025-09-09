import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getDividends } from "../api";
import type { Transaction } from "../types";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { money } from "../lib/money";
import { formatDateISO } from "../lib/date";
import { Sparkline } from "./Sparkline";

export function DividendHistory() {
  const { t } = useTranslation();
  const { data, loading, error } = useFetch<Transaction[]>(() => getDividends(), []);

  const series = useMemo(() => {
    const byDate: Record<string, number> = {};
    (data ?? []).forEach((d) => {
      if (d.date && d.amount_minor != null) {
        byDate[d.date] = (byDate[d.date] || 0) + d.amount_minor / 100;
      }
    });
    return Object.entries(byDate)
      .sort(([a], [b]) => (a > b ? 1 : -1))
      .map(([, amt]) => amt);
  }, [data]);

  const summary = useMemo(() => {
    const map: Record<string, number> = {};
    (data ?? []).forEach((d) => {
      if (d.owner && d.ticker && d.amount_minor != null) {
        const key = `${d.owner}__${d.ticker}`;
        map[key] = (map[key] || 0) + d.amount_minor / 100;
      }
    });
    return Object.entries(map).map(([key, amt]) => {
      const [owner, ticker] = key.split("__");
      return { owner, ticker, amount: amt };
    });
  }, [data]);

  return (
    <div>
      {error && <p style={{ color: "red" }}>{error.message}</p>}
      {loading ? (
        <p>{t("common.loading")}</p>
      ) : (
        <>
          <Sparkline data={series} ariaLabel="Dividend trend" />
          <table className={tableStyles.table} style={{ marginTop: "1rem" }}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>Date</th>
                <th className={tableStyles.cell}>Owner</th>
                <th className={tableStyles.cell}>Ticker</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((d, i) => (
                <tr key={i}>
                  <td className={tableStyles.cell}>
                    {d.date ? formatDateISO(new Date(d.date)) : ""}
                  </td>
                  <td className={tableStyles.cell}>{d.owner}</td>
                  <td className={tableStyles.cell}>{d.ticker}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {d.amount_minor != null
                      ? money(d.amount_minor / 100, d.currency ?? "GBP")
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={{ marginTop: "1rem" }}>Totals</h3>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>Owner</th>
                <th className={tableStyles.cell}>Ticker</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Total</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((s, i) => (
                <tr key={i}>
                  <td className={tableStyles.cell}>{s.owner}</td>
                  <td className={tableStyles.cell}>{s.ticker}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {money(s.amount, "GBP")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default DividendHistory;
