import type { Account } from "../types";
import { money, percent } from "../lib/money";
import { useConfig } from "../ConfigContext";

export type PortfolioTotals = {
  totalValue: number;
  totalGain: number;
  totalDayChange: number;
  totalCost: number;
  totalGainPct: number;
  totalDayChangePct: number;
};

export function computePortfolioTotals(accounts: Account[]): PortfolioTotals {
  let totalValue = 0;
  let totalGain = 0;
  let totalDayChange = 0;
  let totalCost = 0;

  for (const acct of accounts) {
    totalValue += acct.value_estimate_gbp ?? 0;
    for (const h of acct.holdings ?? []) {
      const cost =
        h.cost_basis_gbp && h.cost_basis_gbp > 0
          ? h.cost_basis_gbp
          : h.effective_cost_basis_gbp ?? 0;
      const market = h.market_value_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;
      const dayChg = h.day_change_gbp ?? 0;

      totalCost += cost;
      totalGain += gain;
      totalDayChange += dayChg;
    }
  }

  const totalGainPct = totalCost > 0 ? (totalGain / totalCost) * 100 : 0;
  const totalDayChangePct =
    totalValue - totalDayChange !== 0
      ? (totalDayChange / (totalValue - totalDayChange)) * 100
      : 0;

  return {
    totalValue,
    totalGain,
    totalDayChange,
    totalCost,
    totalGainPct,
    totalDayChangePct,
  };
}

type Props = {
  totals: PortfolioTotals;
};

export function PortfolioSummary({ totals }: Props) {
  const {
    totalValue,
    totalDayChange,
    totalGain,
    totalGainPct,
    totalDayChangePct,
  } = totals;
  const { baseCurrency } = useConfig();

  return (
    <div
      style={{
        display: "flex",
        gap: "2rem",
        margin: "1rem 0",
        padding: "1rem",
        backgroundColor: "#222",
        border: "1px solid #444",
        borderRadius: "6px",
      }}
    >
      <div>
        <div style={{ fontSize: "1rem", color: "#aaa" }}>Total Value</div>
        <div style={{ fontSize: "2rem", fontWeight: "bold" }}>
          {money(totalValue, baseCurrency)}
        </div>
      </div>
      <div>
        <div style={{ fontSize: "1rem", color: "#aaa" }}>Day Change</div>
        <div
          style={{
            fontSize: "2rem",
            fontWeight: "bold",
            color: totalDayChange >= 0 ? "lightgreen" : "red",
          }}
        >
          {money(totalDayChange, baseCurrency)} ({percent(totalDayChangePct)})
        </div>
      </div>
      <div>
        <div style={{ fontSize: "1rem", color: "#aaa" }}>Total Gain</div>
        <div
          style={{
            fontSize: "2rem",
            fontWeight: "bold",
            color: totalGain >= 0 ? "lightgreen" : "red",
          }}
        >
          {money(totalGain, baseCurrency)} ({percent(totalGainPct)})
        </div>
      </div>
    </div>
  );
}

export default PortfolioSummary;

