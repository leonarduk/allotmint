import type { ReactNode } from "react";
import type { Account } from "../types";
import { money, percent } from "../lib/money";
import { useConfig } from "../ConfigContext";
import { isCashInstrument } from "../lib/instruments";
import { LineChart, PiggyBank, TrendingUp, Wallet } from "lucide-react";

export type PortfolioTotals = {
  totalValue: number;
  totalStockValue: number;
  totalCash: number;
  totalGain: number;
  totalDayChange: number;
  totalCost: number;
  totalGainPct: number;
  totalDayChangePct: number;
};

export function computePortfolioTotals(accounts: Account[]): PortfolioTotals {
  let totalValue = 0;
  let totalStockValue = 0;
  let totalCash = 0;
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

      if (isCashInstrument({
        instrument_type: h.instrument_type,
        ticker: h.ticker,
      })) {
        totalCash += market;
      } else {
        totalStockValue += market;
      }

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
    totalStockValue,
    totalCash,
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
    totalStockValue,
    totalCash,
    totalGain,
    totalGainPct,
  } = totals;
  const { baseCurrency } = useConfig();

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "1.5rem",
        margin: "1rem 0",
        padding: "1rem",
        backgroundColor: "#222",
        border: "1px solid #444",
        borderRadius: "6px",
      }}
    >
      <SummaryCard
        label="Stock value"
        icon={<LineChart size={20} />}
        value={money(totalStockValue, baseCurrency)}
      />
      <SummaryCard
        label="Total cash"
        icon={<Wallet size={20} />}
        value={money(totalCash, baseCurrency)}
      />
      <SummaryCard
        label="Total value"
        icon={<PiggyBank size={20} />}
        value={money(totalValue, baseCurrency)}
      />
      <SummaryCard
        label="Gain/loss"
        icon={<TrendingUp size={20} />}
        value={money(totalGain, baseCurrency)}
        accentColor={totalGain >= 0 ? "lightgreen" : "red"}
        secondary={`(${percent(totalGainPct)})`}
      />
    </div>
  );
}

export default PortfolioSummary;

type SummaryCardProps = {
  label: string;
  icon: ReactNode;
  value: string;
  secondary?: string;
  accentColor?: string;
};

function SummaryCard({ label, icon, value, secondary, accentColor }: SummaryCardProps) {
  return (
    <div style={{ minWidth: "12rem", flex: "1 1 12rem" }}>
      <div
        style={{
          fontSize: "1rem",
          color: "#aaa",
          display: "flex",
          alignItems: "center",
          gap: "0.25rem",
        }}
      >
        {icon}
        {label}
      </div>
      <div
        style={{
          fontSize: "2rem",
          fontWeight: "bold",
          color: accentColor,
          display: "flex",
          alignItems: "baseline",
          gap: "0.5rem",
        }}
      >
        <span>{value}</span>
        {secondary && (
          <span
            style={{
              fontSize: "1rem",
              fontWeight: "normal",
              color: accentColor ?? "#aaa",
            }}
          >
            {secondary}
          </span>
        )}
      </div>
    </div>
  );
}

