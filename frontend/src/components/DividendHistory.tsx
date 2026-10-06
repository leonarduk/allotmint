import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { getDividends } from "../api";
import type { Transaction } from "../types";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { normalizeDisplayCurrency } from "../lib/money";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { formatDateISO } from "../lib/date";
import { Sparkline } from "./Sparkline";

const fetchDividends = () => getDividends();

export function DividendHistory() {
  const { t } = useTranslation();
  const reporting = useReportingCurrency();
  // A stable function: an inline arrow is a new `fn` every render, and
  // useFetch refetches whenever `fn` changes -- an endless fetch loop.
  const { data, loading, error } = useFetch<Transaction[]>(fetchDividends, []);

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

  // One total per owner, ticker and currency: amounts in different
  // currencies are never added together (#9805).
  const summary = useMemo(() => {
    const map = new Map<string, { owner: string; ticker: string; currency: string; amount: number }>();
    (data ?? []).forEach((d) => {
      if (d.owner && d.ticker && d.amount_minor != null) {
        const currency = normalizeDisplayCurrency(d.currency || "GBP");
        const key = `${d.owner}__${d.ticker}__${currency}`;
        const entry = map.get(key) ?? { owner: d.owner, ticker: d.ticker, currency, amount: 0 };
        entry.amount += d.amount_minor / 100;
        map.set(key, entry);
      }
    });
    return Array.from(map.values());
  }, [data]);

  return (
    <div>
      {error && <p style={{ color: "red" }}>{error.message}</p>}
      {loading ? (
        <p>{t("common.loading")}</p>
      ) : (
        <>
          <Sparkline data={series} ariaLabel={t("dividendHistory.trendAria")} />
          <table className={tableStyles.table} style={{ marginTop: "1rem" }}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>{t("dividendHistory.date")}</th>
                <th className={tableStyles.cell}>{t("dividendHistory.owner")}</th>
                <th className={tableStyles.cell}>{t("dividendHistory.ticker")}</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("dividendHistory.amount")}</th>
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
                      ? reporting.format(d.amount_minor / 100, d.currency)
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={{ marginTop: "1rem" }}>{t("dividendHistory.totals")}</h3>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>{t("dividendHistory.owner")}</th>
                <th className={tableStyles.cell}>{t("dividendHistory.ticker")}</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("dividendHistory.total")}</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((s, i) => (
                <tr key={i}>
                  <td className={tableStyles.cell}>{s.owner}</td>
                  <td className={tableStyles.cell}>{s.ticker}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {reporting.format(s.amount, s.currency)}
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
