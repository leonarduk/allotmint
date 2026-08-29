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
  /** Non-cash holdings whose gain is excluded from totalGain/totalCost
   * because cost_basis_source === "unknown" (no acquisition date and no
   * booked cost on record, per #7220). Market value from these holdings
   * still counts toward totalValue/totalStockValue/totalCash -- only the
   * *gain* figures, which the app cannot honestly compute, are excluded. */
  unknownCostBasisCount: number;
  /** Non-cash holdings considered for gain at all (denominator for the
   * "excludes N of M" wording). */
  gainEligibleHoldingCount: number;
};

// eslint-disable-next-line react-refresh/only-export-components
export function computePortfolioTotals(accounts: Account[]): PortfolioTotals {
  let totalValue = 0;
  let totalStockValue = 0;
  let totalCash = 0;
  let totalGain = 0;
  let totalDayChange = 0;
  let totalCost = 0;
  let unknownCostBasisCount = 0;
  let gainEligibleHoldingCount = 0;

  for (const acct of accounts) {
    totalValue += acct.value_estimate_gbp ?? 0;
    for (const h of acct.holdings ?? []) {
      const market = h.market_value_gbp ?? 0;
      const dayChg = h.day_change_gbp ?? 0;

      if (isCashInstrument({
        instrument_type: h.instrument_type,
        ticker: h.ticker,
      })) {
        totalCash += market;
      } else {
        totalStockValue += market;
      }
      totalDayChange += dayChg;
      gainEligibleHoldingCount += 1;

      // A holding with no acquisition date and no booked cost has its cost
      // basis fabricated to equal market value (see backend/common/
      // holding_utils.py), which makes gain read as a confident £0.00 --
      // indistinguishable from "you broke even". Excluding it from the
      // gain/cost totals (rather than summing that fabricated zero) keeps
      // the headline figure honest; the per-row cells already render N/A
      // for the same reason (HoldingsTable.tsx).
      if (h.cost_basis_source === "unknown") {
        unknownCostBasisCount += 1;
        continue;
      }

      const cost =
        h.cost_basis_gbp && h.cost_basis_gbp > 0
          ? h.cost_basis_gbp
          : h.effective_cost_basis_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;

      totalCost += cost;
      totalGain += gain;
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
    unknownCostBasisCount,
    gainEligibleHoldingCount,
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
    unknownCostBasisCount,
    gainEligibleHoldingCount,
  } = totals;
  const { baseCurrency } = useConfig();

  // When every holding's cost basis is unknown, totalCost/totalGain are both
  // zero -- not because the portfolio broke even, but because there is
  // nothing to compute from. Say so rather than showing a confident £0.00.
  const allGainUnknown =
    gainEligibleHoldingCount > 0 &&
    unknownCostBasisCount === gainEligibleHoldingCount;
  const gainNote = allGainUnknown
    ? `Gain unavailable for all ${gainEligibleHoldingCount} holdings (no cost basis on record)`
    : unknownCostBasisCount > 0
      ? `Excludes ${unknownCostBasisCount} of ${gainEligibleHoldingCount} holdings with no cost basis on record`
      : undefined;

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
        value={allGainUnknown ? "—" : money(totalGain, baseCurrency)}
        accentColor={
          allGainUnknown ? undefined : totalGain >= 0 ? "lightgreen" : "red"
        }
        secondary={allGainUnknown ? undefined : `(${percent(totalGainPct)})`}
        note={gainNote}
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
  note?: string;
};

function SummaryCard({
  label,
  icon,
  value,
  secondary,
  accentColor,
  note,
}: SummaryCardProps) {
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
          color: accentColor ?? "#eee",
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
      {note && (
        <div
          role="status"
          style={{ fontSize: "0.75rem", color: "#aaa", marginTop: "0.25rem" }}
        >
          {note}
        </div>
      )}
    </div>
  );
}
