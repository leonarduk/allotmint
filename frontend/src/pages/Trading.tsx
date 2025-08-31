import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTradingSignals } from "../api";
import type { TradingSignal } from "../types";
import { InstrumentDetail } from "../components/InstrumentDetail";
import tableStyles from "../styles/table.module.css";

export default function Trading() {
  const { t } = useTranslation();
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    getTradingSignals()
      .then(setSignals)
      .catch((e) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  if (error) {
    return <p style={{ color: "red" }}>{error}</p>;
  }

  if (!signals.length) {
    return <p>{t("trading.noSignals")}</p>;
  }

  return (
    <>
      <table className={tableStyles.table}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>Ticker</th>
            <th className={tableStyles.cell}>Action</th>
            <th className={tableStyles.cell}>Reason</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr key={s.ticker}>
              <td
                className={`${tableStyles.cell} ${tableStyles.clickable}`}
                onClick={() => setSelected(s.ticker)}
              >
                {s.ticker}
              </td>
              <td className={tableStyles.cell}>{s.action}</td>
              <td className={tableStyles.cell}>{s.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && (
        <InstrumentDetail ticker={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
