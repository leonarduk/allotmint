import { useState } from "react";
import type { Holding } from "../types";
import { money } from "../lib/money";
import styles from "../styles/table.module.css";

type SortKey = "ticker" | "name" | "cost" | "gain" | "gain_pct" | "days_held";

type Props = {
  holdings: Holding[];
  onSelectInstrument?: (ticker: string, name: string) => void;
};

export function HoldingsTable({ holdings, onSelectInstrument }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("ticker");
  const [asc, setAsc] = useState(true);

  if (!holdings.length) return null;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setAsc(!asc);
    } else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const rows = holdings.map((h) => {
    const cost =
      (h.cost_basis_gbp ?? 0) > 0
        ? h.cost_basis_gbp ?? 0
        : h.effective_cost_basis_gbp ?? 0;

    const market = h.market_value_gbp ?? 0;
    const gain =
      h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
        ? h.gain_gbp
        : market - cost;

    const gain_pct =
      h.gain_pct !== undefined && h.gain_pct !== null
        ? h.gain_pct
        : cost
          ? (gain / cost) * 100
          : 0;

    return { ...h, cost, market, gain, gain_pct };
  });

  const sorted = [...rows].sort((a, b) => {
    const va = a[sortKey as keyof typeof a];
    const vb = b[sortKey as keyof typeof b];
    if (typeof va === "string" && typeof vb === "string") {
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    const na = (va as number) ?? 0;
    const nb = (vb as number) ?? 0;
    return asc ? na - nb : nb - na;
  });

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th
            className={`${styles.cell} ${styles.clickable}`}
            onClick={() => handleSort("ticker")}
          >
            Ticker{sortKey === "ticker" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            className={`${styles.cell} ${styles.clickable}`}
            onClick={() => handleSort("name")}
          >
            Name{sortKey === "name" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={styles.cell}>CCY</th>
          <th className={`${styles.cell} ${styles.right}`}>Units</th>
          <th className={`${styles.cell} ${styles.right}`}>Px £</th>
          <th
            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
            onClick={() => handleSort("cost")}
          >
            Cost £{sortKey === "cost" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${styles.cell} ${styles.right}`}>Mkt £</th>
          <th
            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
            onClick={() => handleSort("gain")}
          >
            Gain £{sortKey === "gain" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th
            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
            onClick={() => handleSort("gain_pct")}
          >
            Gain %{sortKey === "gain_pct" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={styles.cell}>Acquired</th>
          <th
            className={`${styles.cell} ${styles.right} ${styles.clickable}`}
            onClick={() => handleSort("days_held")}
          >
            Days&nbsp;Held{sortKey === "days_held" ? (asc ? " ▲" : " ▼") : ""}
          </th>
          <th className={`${styles.cell} ${styles.center}`}>Eligible?</th>
        </tr>
      </thead>

      <tbody>
        {sorted.map((h) => {
          const handleClick = (e: React.MouseEvent) => {
            e.preventDefault();
            onSelectInstrument?.(h.ticker, h.name ?? h.ticker);
          };

          return (
            <tr key={h.ticker + h.acquired_date}>
              <td className={styles.cell}>
                <a
                  href="#"
                  onClick={handleClick}
                  className={styles.link}
                >
                  {h.ticker}
                </a>
              </td>
              <td className={styles.cell}>{h.name}</td>
              <td className={styles.cell}>{h.currency ?? "—"}</td>
              <td className={styles.cell}>{h.instrument_type ?? "—"}</td>
              <td className={`${styles.cell} ${styles.right}`}>{h.units.toLocaleString()}</td>
              <td className={`${styles.cell} ${styles.right}`}>{money(h.current_price_gbp)}</td>
              <td
                className={`${styles.cell} ${styles.right}`}
                title={
                  (h.cost_basis_gbp ?? 0) > 0
                    ? "Actual purchase cost"
                    : "Inferred from price on acquisition date"
                }
              >
                {money(h.cost)}
              </td>
              <td className={`${styles.cell} ${styles.right}`}>{money(h.market)}</td>
              <td
                className={`${styles.cell} ${styles.right}`}
                style={{
                  color: h.gain >= 0 ? "lightgreen" : "red",
                }}
              >
                {money(h.gain)}
              </td>
              <td
                className={`${styles.cell} ${styles.right}`}
                style={{
                  color: h.gain_pct >= 0 ? "lightgreen" : "red",
                }}
              >
                {Number.isFinite(h.gain_pct) ? h.gain_pct.toFixed(1) : "—"}
              </td>
              <td className={styles.cell}>{h.acquired_date}</td>
              <td className={`${styles.cell} ${styles.right}`}>{h.days_held ?? "—"}</td>
              <td
                className={`${styles.cell} ${styles.center}`}
                style={{
                  color: h.sell_eligible ? "lightgreen" : "gold",
                }}
              >
                {h.sell_eligible ? "✓ Eligible" : `✗ ${h.days_until_eligible ?? ""}`}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
