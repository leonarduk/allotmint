import type { ReactNode } from "react";
import type { Account } from "../types";
import { money, percent } from "../lib/money";
import { useConfig } from "../ConfigContext";
import { isCashInstrument } from "../lib/instruments";
import { isCostBasisUnreliable } from "../lib/costBasis";
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
   * because their cost basis is unreliable: cost_basis_source "unknown" (no
   * acquisition date and no booked cost on record, per #7220) or
   * "book_suspect" (implausible booked cost, #8472). Market value from these holdings
   * still counts toward totalValue/totalStockValue/totalCash -- only the
   * *gain* figures, which the app cannot honestly compute, are excluded. */
  unknownCostBasisCount: number;
  /** Non-cash holdings considered for gain at all (denominator for the
   * "excludes N of M" wording). */
  gainEligibleHoldingCount: number;
  /** Non-cash holdings with no market value (no price), excluded from
   * totalGain/totalCost (#8607). Without a price their gain cannot be
   * computed; treating the missing value as £0 would book their whole cost
   * as a loss. Counted separately from unknownCostBasisCount (a holding is
   * counted in at most one of the two). */
  unpricedHoldingCount: number;
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
  let unpricedHoldingCount = 0;

  for (const acct of accounts) {
    totalValue += acct.value_estimate_gbp ?? 0;
    for (const h of acct.holdings ?? []) {
      const market = h.market_value_gbp ?? 0;
      const dayChg = h.day_change_gbp ?? 0;
      const isCash = isCashInstrument({
        instrument_type: h.instrument_type,
        ticker: h.ticker,
      });

      if (isCash) {
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
      // for the same reason (HoldingsTable.tsx). An implausible booked cost
      // ("book_suspect", #8472) is excluded for the same reason: summing its
      // tiny cost would inflate the headline gain by orders of magnitude.
      if (isCostBasisUnreliable(h.cost_basis_source)) {
        unknownCostBasisCount += 1;
        continue;
      }

      // An unpriced non-cash holding (#8607) has no market value, so its
      // gain cannot be computed. Falling through would compute
      // `0 - cost` and book its whole cost as a loss (headline -100%).
      if (!isCash && (h.market_value_gbp === null || h.market_value_gbp === undefined)) {
        unpricedHoldingCount += 1;
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
    unpricedHoldingCount,
  };
}

function buildGainNote(
  unknownCostBasisCount: number,
  unpricedHoldingCount: number,
  gainEligibleHoldingCount: number,
  allGainUnknown: boolean,
): string | undefined {
  if (allGainUnknown) {
    const reason =
      unpricedHoldingCount === 0
        ? "no reliable cost basis"
        : unknownCostBasisCount === 0
          ? "no price"
          : "no reliable cost basis or no price";
    return `Gain unavailable for all ${gainEligibleHoldingCount} holdings (${reason})`;
  }
  if (unknownCostBasisCount > 0 && unpricedHoldingCount > 0) {
    return `Excludes ${unknownCostBasisCount} of ${gainEligibleHoldingCount} holdings with no reliable cost basis and ${unpricedHoldingCount} with no price`;
  }
  if (unknownCostBasisCount > 0) {
    return `Excludes ${unknownCostBasisCount} of ${gainEligibleHoldingCount} holdings with no reliable cost basis`;
  }
  if (unpricedHoldingCount > 0) {
    return `Excludes ${unpricedHoldingCount} of ${gainEligibleHoldingCount} holdings with no price`;
  }
  return undefined;
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
    unpricedHoldingCount,
  } = totals;
  const { baseCurrency } = useConfig();

  // When every holding is excluded (unknown cost basis or no price),
  // totalCost/totalGain are both zero -- not because the portfolio broke
  // even, but because there is nothing to compute from. Say so rather than
  // showing a confident £0.00.
  const allGainUnknown =
    gainEligibleHoldingCount > 0 &&
    unknownCostBasisCount + unpricedHoldingCount === gainEligibleHoldingCount;
  const gainNote = buildGainNote(
    unknownCostBasisCount,
    unpricedHoldingCount,
    gainEligibleHoldingCount,
    allGainUnknown,
  );

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
